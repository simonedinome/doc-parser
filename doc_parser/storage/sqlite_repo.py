"""Repository v1: run su SQLite (WAL), file su filesystem locale."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from doc_parser.core.models import RunRecord, RunStatus, utcnow
from doc_parser.storage.base import AggregateBy, Repository

_COLUMNS: list[str] = list(RunRecord.model_fields.keys())

_AGGREGATE_KEYS: dict[str, str] = {
    "run": "run_id",
    "session": "session_id",
    "user": "requester_upn",
}

_DATETIME_FIELDS = {"created_at", "started_at", "completed_at"}


class SqliteRepository(Repository):
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._inbox_dir = self._data_dir / "inbox"
        self._outputs_dir = self._data_dir / "outputs"
        for directory in (self._data_dir, self._inbox_dir, self._outputs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "runs.db"
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        columns_sql = ",\n".join(
            f"    {name} {'TEXT PRIMARY KEY' if name == 'run_id' else _column_type(name)}"
            for name in _COLUMNS
        )
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(f"CREATE TABLE IF NOT EXISTS runs (\n{columns_sql}\n)")
            _add_missing_columns(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_input_hash ON runs(input_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status, created_at)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_requester ON runs(requester_upn, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_parent ON runs(parent_run_id)"
            )

    # --- Run ---

    def create_run(self, run: RunRecord) -> RunRecord:
        values = _to_row(run)
        placeholders = ", ".join("?" for _ in _COLUMNS)
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO runs ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                [values[c] for c in _COLUMNS],
            )
        return run

    def claim_next_queued(self) -> RunRecord | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT run_id FROM runs WHERE status = ? "
                    "ORDER BY created_at, run_id LIMIT 1",
                    (RunStatus.QUEUED.value,),
                ).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    return None
                run_id = row["run_id"]
                cursor = conn.execute(
                    "UPDATE runs SET status = ?, started_at = ? "
                    "WHERE run_id = ? AND status = ?",
                    (
                        RunStatus.PROCESSING.value,
                        utcnow().isoformat(),
                        run_id,
                        RunStatus.QUEUED.value,
                    ),
                )
                if cursor.rowcount != 1:
                    conn.execute("ROLLBACK")
                    return None
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        return self.get_run(run_id)

    def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        unknown = set(fields) - set(_COLUMNS)
        if unknown:
            raise ValueError(f"Campi run sconosciuti: {sorted(unknown)}")
        assignments = ", ".join(f"{name} = ?" for name in fields)
        values = [_serialize(name, value) for name, value in fields.items()]
        with self._connect() as conn:
            conn.execute(f"UPDATE runs SET {assignments} WHERE run_id = ?", [*values, run_id])

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return _from_row(row) if row else None

    def list_runs(
        self,
        requester_upn: str | None = None,
        status: RunStatus | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
    ) -> list[RunRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if requester_upn is not None:
            clauses.append("requester_upn = ?")
            params.append(requester_upn)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since.isoformat())
        if until is not None:
            clauses.append("created_at <= ?")
            params.append(until.isoformat())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM runs {where} ORDER BY created_at DESC, run_id DESC LIMIT ?",
                [*params, limit],
            ).fetchall()
        return [_from_row(row) for row in rows]

    def aggregate_costs(
        self,
        by: AggregateBy,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        key = _AGGREGATE_KEYS[by]
        clauses: list[str] = []
        params: list[Any] = []
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since.isoformat())
        if until is not None:
            clauses.append("created_at <= ?")
            params.append(until.isoformat())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {key} AS group_key,
                       COUNT(*) AS run_count,
                       COALESCE(SUM(tokens_in), 0) AS tokens_in,
                       COALESCE(SUM(tokens_out), 0) AS tokens_out,
                       COALESCE(SUM(tokens_total), 0) AS tokens_total,
                       COALESCE(SUM(cost_eur), 0.0) AS cost_eur
                FROM runs {where}
                GROUP BY {key}
                ORDER BY cost_eur DESC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def find_done_by_hash(self, input_hash: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE input_hash = ? AND status = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (input_hash, RunStatus.DONE.value),
            ).fetchone()
        return _from_row(row) if row else None

    # --- File ---

    def save_input_file(self, run_id: str, filename: str, data: bytes) -> str:
        return self._save(self._inbox_dir, run_id, filename, data)

    def save_output_file(self, run_id: str, filename: str, data: bytes) -> str:
        return self._save(self._outputs_dir, run_id, filename, data)

    def get_file(self, ref: str) -> bytes:
        return Path(ref).read_bytes()

    def _save(self, directory: Path, run_id: str, filename: str, data: bytes) -> str:
        path = directory / f"{run_id}_{_sanitize(filename)}"
        path.write_bytes(data)
        return str(path)


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Migrazione additiva: un runs.db creato con uno schema precedente riceve
    le colonne aggiunte nel frattempo a RunRecord (CREATE TABLE IF NOT EXISTS
    non tocca una tabella già esistente)."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
    for name in _COLUMNS:
        if name in existing:
            continue
        try:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {_column_type(name)}")
        except sqlite3.OperationalError as exc:
            # UI e CLI possono migrare lo stesso DB in parallelo.
            if "duplicate column name" not in str(exc).lower():
                raise


def _column_type(name: str) -> str:
    annotation = str(RunRecord.model_fields[name].annotation)
    if "int" in annotation or "bool" in annotation:
        return "INTEGER"
    if "float" in annotation:
        return "REAL"
    return "TEXT"


def _serialize(name: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, RunStatus):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


def _to_row(run: RunRecord) -> dict[str, Any]:
    return {name: _serialize(name, getattr(run, name)) for name in _COLUMNS}


def _from_row(row: sqlite3.Row) -> RunRecord:
    data = dict(row)
    for field in _DATETIME_FIELDS:
        if data.get(field):
            data[field] = datetime.fromisoformat(data[field])
    data["notified"] = bool(data.get("notified"))
    return RunRecord(**data)


def _sanitize(filename: str) -> str:
    name = Path(filename).name
    return re.sub(r"[^\w.\- ]", "_", name) or "file"
