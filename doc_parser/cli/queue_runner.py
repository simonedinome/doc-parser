"""Esecuzione della coda di run (YAML o batch): parallelismo, checkpoint/resume,
sullo stesso motore condiviso con la UI (Worker + Repository + pipeline.core) —
zero logica di elaborazione duplicata rispetto a doc_parser.ui.views.elabora."""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tempfile import TemporaryDirectory

from doc_parser.cli.config import GlobalSettings, RunConfig, RunsConfig, load_runs_config, resolve_run_settings
from doc_parser.core.models import RunRecord, RunStatus
from doc_parser.ingestion import guardrails
from doc_parser.ingestion.downloader import download_url
from doc_parser.settings import Settings
from doc_parser.storage.sqlite_repo import SqliteRepository
from doc_parser.worker.processor import Worker

logger = logging.getLogger(__name__)

_VIDEO_CONTENT_TYPES = {"screencast", "webinar", "hybrid"}
_checkpoint_lock = threading.Lock()


def _load_checkpoint(path: Path) -> dict:
    if not path.exists():
        return {"completed_runs": [], "failed_runs": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"completed_runs": [], "failed_runs": {}}


def _save_checkpoint(path: Path, checkpoint: dict) -> None:
    with _checkpoint_lock:
        path.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8")


def _resolve_files(run_config: RunConfig, tmp_dir: Path) -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    for item in run_config.inputs:
        if item.source == "url":
            path = download_url(item.url, tmp_dir)
            files.append((path.name, path.read_bytes()))
        else:
            local_path = Path(item.path)
            if not local_path.exists():
                raise FileNotFoundError(f"File non trovato: {item.path!r}")
            files.append((local_path.name, local_path.read_bytes()))
    return files


def _process_run_config(
    run_config: RunConfig,
    global_settings: GlobalSettings,
    repo: SqliteRepository,
    worker: Worker,
    settings: Settings,
) -> RunRecord:
    effective = resolve_run_settings(global_settings, run_config.settings)
    is_video = effective["content_type"] in _VIDEO_CONTENT_TYPES

    with TemporaryDirectory(prefix="doc_parser_cli_") as tmp_dir:
        files = _resolve_files(run_config, Path(tmp_dir))

        input_type = guardrails.resolve_input_type(is_video, [f[0] for f in files])
        total_size = sum(len(data) for _, data in files)
        guardrails.check_size(total_size, settings.max_upload_mb)

        # Per una singola run-file, input_filename deve essere il nome file reale
        # (con estensione): la pipeline lo rilegge per la classificazione guardrail
        # quando ricarica una run a file singolo da storage. Per le run multi-file
        # (merge) usiamo invece il nome logico della run YAML come etichetta.
        input_filename = files[0][0] if len(files) == 1 else run_config.name

        run = RunRecord(
            session_id=f"cli-{run_config.name}",
            requester_upn=global_settings.requester_upn,
            input_filename=input_filename,
            input_type=input_type,
            content_type=effective["content_type"] if is_video else None,
            output_mode=effective["output_mode"],
            output_artifacts=effective["output_artifacts"],
            language=effective["language"],
            model_id=effective["model_id"],
        )
        if len(files) == 1:
            filename, data = files[0]
            run.input_size_bytes = len(data)
            run.input_path = repo.save_input_file(run.run_id, filename, data)
        else:
            manifest = []
            for filename, data in files:
                ref = repo.save_input_file(run.run_id, filename, data)
                manifest.append({"filename": filename, "path_ref": ref})
            run.input_size_bytes = sum(len(data) for _, data in files)
            run.input_manifest_ref = repo.save_input_file(
                run.run_id, "manifest.json", json.dumps(manifest).encode("utf-8")
            )
        repo.create_run(run)

    worker.process_run(run)
    return repo.get_run(run.run_id)


def run_queue(config: RunsConfig, settings: Settings, checkpoint_path: Path | None = None) -> dict:
    """Esegue tutte le run pendenti di *config* con parallelismo e checkpoint.

    Ritorna il checkpoint finale ``{"completed_runs": [...], "failed_runs": {...}}``.
    """
    checkpoint_path = checkpoint_path or (settings.data_dir / "runs_checkpoint.json")
    checkpoint = _load_checkpoint(checkpoint_path)
    completed = set(checkpoint.get("completed_runs", []))

    pending = [r for r in config.runs if r.name not in completed]
    if not pending:
        logger.info("Nessuna run da eseguire (tutte già completate).")
        return checkpoint

    repo = SqliteRepository(data_dir=settings.data_dir)
    worker = Worker(repo=repo, settings=settings)

    logger.info(
        "Avvio %d run con al massimo %d worker paralleli.", len(pending), config.settings.parallel_runs
    )

    with ThreadPoolExecutor(max_workers=config.settings.parallel_runs) as executor:
        futures = {
            executor.submit(_process_run_config, run_config, config.settings, repo, worker, settings): run_config
            for run_config in pending
        }
        for future in as_completed(futures):
            run_config = futures[future]
            try:
                result = future.result()
                if result is not None and result.status in (RunStatus.DONE, RunStatus.DUPLICATE):
                    checkpoint.setdefault("completed_runs", []).append(run_config.name)
                    checkpoint.setdefault("failed_runs", {}).pop(run_config.name, None)
                    logger.info("Run '%s' completata (%s).", run_config.name, result.status.value)
                else:
                    error = result.error_message if result is not None else "stato sconosciuto"
                    checkpoint.setdefault("failed_runs", {})[run_config.name] = error or "errore sconosciuto"
                    logger.error("Run '%s' fallita: %s", run_config.name, error)
            except Exception as exc:
                checkpoint.setdefault("failed_runs", {})[run_config.name] = f"{type(exc).__name__}: {exc}"
                logger.error("Run '%s' fallita: %s", run_config.name, exc)
            _save_checkpoint(checkpoint_path, checkpoint)

    return checkpoint


def run_yaml_queue(runs_file: Path, settings: Settings, checkpoint_path: Path | None = None) -> dict:
    config = load_runs_config(runs_file)
    return run_queue(config, settings, checkpoint_path)
