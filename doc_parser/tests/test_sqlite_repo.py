import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from doc_parser.core.models import RunRecord, RunStatus
from doc_parser.storage.sqlite_repo import SqliteRepository


@pytest.fixture
def repo(tmp_path: Path) -> SqliteRepository:
    return SqliteRepository(data_dir=tmp_path / "data")


def _run(**overrides) -> RunRecord:
    base = dict(
        session_id="sess-1",
        requester_upn="utente@demo.local",
        input_filename="doc1.pdf",
    )
    base.update(overrides)
    return RunRecord(**base)


def test_create_and_get_roundtrip(repo: SqliteRepository) -> None:
    run = _run(
        input_hash="abc123",
        input_size_bytes=1024,
        input_pages=3,
        tokens_in=100,
        tokens_out=20,
        tokens_total=120,
        unit_price_in=0.28,
        unit_price_out=2.3,
        cost_eur=0.000074,
        chunk_count=2,
        uncertainty_count=1,
        notified=True,
    )
    repo.create_run(run)
    loaded = repo.get_run(run.run_id)
    assert loaded == run


def test_get_missing_run_returns_none(repo: SqliteRepository) -> None:
    assert repo.get_run("inesistente") is None


def test_update_run_fields(repo: SqliteRepository) -> None:
    run = repo.create_run(_run())
    completed = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    repo.update_run(
        run.run_id,
        status=RunStatus.DONE,
        completed_at=completed,
        cost_eur=0.5,
        error_message=None,
    )
    loaded = repo.get_run(run.run_id)
    assert loaded is not None
    assert loaded.status == RunStatus.DONE
    assert loaded.completed_at == completed
    assert loaded.cost_eur == 0.5


def test_update_run_unknown_field_raises(repo: SqliteRepository) -> None:
    run = repo.create_run(_run())
    with pytest.raises(ValueError, match="sconosciuti"):
        repo.update_run(run.run_id, campo_inventato=1)


def test_list_runs_filters(repo: SqliteRepository) -> None:
    now = datetime.now(timezone.utc)
    old = repo.create_run(_run(created_at=now - timedelta(days=2)))
    recent = repo.create_run(_run(created_at=now, requester_upn="altro@demo.local"))
    done = repo.create_run(_run(created_at=now - timedelta(hours=1), status=RunStatus.DONE))

    all_runs = repo.list_runs()
    assert [r.run_id for r in all_runs] == [recent.run_id, done.run_id, old.run_id]

    assert [r.run_id for r in repo.list_runs(requester_upn="altro@demo.local")] == [recent.run_id]
    assert [r.run_id for r in repo.list_runs(status=RunStatus.DONE)] == [done.run_id]
    assert [r.run_id for r in repo.list_runs(since=now - timedelta(hours=2))] == [
        recent.run_id,
        done.run_id,
    ]
    assert len(repo.list_runs(limit=1)) == 1


def test_claim_takes_oldest_queued(repo: SqliteRepository) -> None:
    now = datetime.now(timezone.utc)
    first = repo.create_run(_run(created_at=now - timedelta(minutes=5)))
    repo.create_run(_run(created_at=now))

    claimed = repo.claim_next_queued()
    assert claimed is not None
    assert claimed.run_id == first.run_id
    assert claimed.status == RunStatus.PROCESSING
    assert claimed.started_at is not None


def test_claim_empty_queue_returns_none(repo: SqliteRepository) -> None:
    assert repo.claim_next_queued() is None


def test_claim_concurrent_single_winner(repo: SqliteRepository) -> None:
    repo.create_run(_run())
    barrier = threading.Barrier(2)
    results: list[RunRecord | None] = [None, None]

    def worker(slot: int) -> None:
        barrier.wait()
        results[slot] = repo.claim_next_queued()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    assert winners[0].status == RunStatus.PROCESSING


def test_find_done_by_hash_ignores_non_done(repo: SqliteRepository) -> None:
    repo.create_run(_run(input_hash="h1", status=RunStatus.FAILED))
    assert repo.find_done_by_hash("h1") is None

    done = repo.create_run(_run(input_hash="h1", status=RunStatus.DONE))
    found = repo.find_done_by_hash("h1")
    assert found is not None and found.run_id == done.run_id
    assert repo.find_done_by_hash("h2") is None


def test_aggregate_costs_by_user_and_session(repo: SqliteRepository) -> None:
    repo.create_run(
        _run(requester_upn="a@x", session_id="s1", tokens_in=100, tokens_out=10, tokens_total=110, cost_eur=1.0)
    )
    repo.create_run(
        _run(requester_upn="a@x", session_id="s2", tokens_in=200, tokens_out=20, tokens_total=220, cost_eur=2.0)
    )
    repo.create_run(
        _run(requester_upn="b@x", session_id="s3", tokens_in=50, tokens_out=5, tokens_total=55, cost_eur=0.5)
    )

    by_user = {row["group_key"]: row for row in repo.aggregate_costs(by="user")}
    assert by_user["a@x"]["run_count"] == 2
    assert by_user["a@x"]["tokens_total"] == 330
    assert by_user["a@x"]["cost_eur"] == pytest.approx(3.0)
    assert by_user["b@x"]["cost_eur"] == pytest.approx(0.5)

    by_session = {row["group_key"]: row for row in repo.aggregate_costs(by="session")}
    assert len(by_session) == 3

    by_run = repo.aggregate_costs(by="run")
    assert all(row["run_count"] == 1 for row in by_run)


def test_aggregate_costs_period_filter(repo: SqliteRepository) -> None:
    now = datetime.now(timezone.utc)
    repo.create_run(_run(created_at=now - timedelta(days=10), cost_eur=5.0))
    repo.create_run(_run(created_at=now, cost_eur=1.0))

    rows = repo.aggregate_costs(by="user", since=now - timedelta(days=1))
    assert len(rows) == 1
    assert rows[0]["cost_eur"] == pytest.approx(1.0)


def test_save_and_get_files(repo: SqliteRepository, tmp_path: Path) -> None:
    ref_in = repo.save_input_file("run1", "il mio doc.pdf", b"%PDF-input")
    ref_out = repo.save_output_file("run1", "il mio doc.txt", b"testo output")

    assert "run1_" in ref_in and "inbox" in ref_in
    assert "run1_" in ref_out and "outputs" in ref_out
    assert repo.get_file(ref_in) == b"%PDF-input"
    assert repo.get_file(ref_out) == b"testo output"


def test_save_file_sanitizes_filename(repo: SqliteRepository) -> None:
    ref = repo.save_input_file("run2", "../../etc/passwd", b"x")
    assert "etc" not in Path(ref).parent.name
    assert Path(ref).parent.name == "inbox"
    assert repo.get_file(ref) == b"x"


_NEW_COLUMNS = {
    "consolidation_model",
    "consolidation_tokens_in",
    "consolidation_tokens_out",
    "consolidation_cost_eur",
}


def _create_old_schema_db(data_dir: Path) -> None:
    import sqlite3

    from doc_parser.storage.sqlite_repo import _COLUMNS, _column_type, _to_row

    data_dir.mkdir(parents=True, exist_ok=True)
    old_columns = [c for c in _COLUMNS if c not in _NEW_COLUMNS]
    columns_sql = ", ".join(
        f"{name} {'TEXT PRIMARY KEY' if name == 'run_id' else _column_type(name)}" for name in old_columns
    )
    conn = sqlite3.connect(data_dir / "runs.db")
    conn.execute(f"CREATE TABLE runs ({columns_sql})")
    row = _to_row(_run(run_id="vecchia", status=RunStatus.DONE))
    conn.execute(
        f"INSERT INTO runs ({', '.join(old_columns)}) VALUES ({', '.join('?' for _ in old_columns)})",
        [row[c] for c in old_columns],
    )
    conn.commit()
    conn.close()


def test_old_schema_db_is_migrated_and_accepts_new_fields(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _create_old_schema_db(data_dir)

    repo = SqliteRepository(data_dir=data_dir)

    old = repo.get_run("vecchia")
    assert old is not None and old.consolidation_cost_eur is None

    run = repo.create_run(
        _run(
            consolidation_model="anthropic/claude-haiku-4.5",
            consolidation_tokens_in=1200,
            consolidation_tokens_out=340,
            consolidation_cost_eur=0.0123,
        )
    )
    loaded = repo.get_run(run.run_id)
    assert loaded == run

    repo.update_run(run.run_id, consolidation_cost_eur=0.5)
    assert repo.get_run(run.run_id).consolidation_cost_eur == 0.5


def test_migration_is_idempotent(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _create_old_schema_db(data_dir)
    SqliteRepository(data_dir=data_dir)
    repo = SqliteRepository(data_dir=data_dir)
    assert repo.get_run("vecchia") is not None


def test_old_schema_without_resume_column_is_migrated(tmp_path: Path) -> None:
    import sqlite3

    from doc_parser.storage.sqlite_repo import _COLUMNS, _column_type, _to_row

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    old_columns = [c for c in _COLUMNS if c != "resume_of_run_id"]
    columns_sql = ", ".join(
        f"{name} {'TEXT PRIMARY KEY' if name == 'run_id' else _column_type(name)}" for name in old_columns
    )
    conn = sqlite3.connect(data_dir / "runs.db")
    conn.execute(f"CREATE TABLE runs ({columns_sql})")
    row = _to_row(_run(run_id="madre"))
    conn.execute(
        f"INSERT INTO runs ({', '.join(old_columns)}) VALUES ({', '.join('?' for _ in old_columns)})",
        [row[c] for c in old_columns],
    )
    conn.commit()
    conn.close()

    repo = SqliteRepository(data_dir=data_dir)

    assert repo.get_run("madre").resume_of_run_id is None
    child = repo.create_run(_run(resume_of_run_id="madre"))
    assert repo.get_run(child.run_id).resume_of_run_id == "madre"


def test_get_output_file_reads_what_save_output_file_wrote(repo: SqliteRepository) -> None:
    repo.save_output_file("run9", "step1_v1.json", b'{"a": 1}')
    assert repo.get_output_file("run9", "step1_v1.json") == b'{"a": 1}'


def test_get_output_file_uses_same_sanitized_name(repo: SqliteRepository) -> None:
    repo.save_output_file("run9", "nome con/barra?.json", b"x")
    assert repo.get_output_file("run9", "nome con/barra?.json") == b"x"


def test_get_output_file_missing_returns_none(repo: SqliteRepository) -> None:
    assert repo.get_output_file("run9", "step1_v7.json") is None
    assert repo.get_output_file("altra-run", "step1_v1.json") is None
