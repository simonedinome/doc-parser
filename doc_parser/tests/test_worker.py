"""Test delle meccaniche di coda del worker (indipendenti da provider/pipeline).

La logica di parsing è delegata alla pipeline condivisa (Fase 4): qui si
verifica solo che Worker gestisca correttamente claim, retry di sistema,
recover delle run stale e la garanzia di non lasciare mai una run in
Processing, iniettando una process_fn fittizia al posto della pipeline reale.
"""

import time
from pathlib import Path

import pytest

from doc_parser.core.models import RunRecord, RunStatus
from doc_parser.settings import Settings
from doc_parser.storage.sqlite_repo import SqliteRepository
from doc_parser.worker.processor import GuardrailRejection, Worker, finalize_run


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        worker_poll_seconds=0.05,
    )


@pytest.fixture
def repo(settings: Settings) -> SqliteRepository:
    return SqliteRepository(data_dir=settings.data_dir)


def _submit(repo: SqliteRepository, filename: str = "doc1.pdf") -> RunRecord:
    run = RunRecord(session_id="s1", requester_upn="utente@demo.local", input_filename=filename)
    return repo.create_run(run)


def _claim_and_process(worker: Worker, repo: SqliteRepository) -> RunRecord:
    claimed = repo.claim_next_queued()
    assert claimed is not None
    worker.process_run(claimed)
    updated = repo.get_run(claimed.run_id)
    assert updated is not None
    return updated


def test_successful_process_fn_reaches_done(repo, settings) -> None:
    def process_fn(run, repo, settings):
        finalize_run(repo, run.run_id, RunStatus.DONE, run.started_at)

    _submit(repo)
    run = _claim_and_process(Worker(repo=repo, settings=settings, process_fn=process_fn), repo)
    assert run.status == RunStatus.DONE
    assert run.completed_at is not None and run.duration_ms is not None


def test_guardrail_rejection_sets_rejected(repo, settings) -> None:
    def process_fn(run, repo, settings):
        raise GuardrailRejection("input non valido")

    _submit(repo)
    run = _claim_and_process(Worker(repo=repo, settings=settings, process_fn=process_fn), repo)
    assert run.status == RunStatus.REJECTED
    assert run.error_message == "input non valido"


def test_generic_exception_sets_failed(repo, settings) -> None:
    def process_fn(run, repo, settings):
        raise RuntimeError("crash inatteso")

    _submit(repo)
    run = _claim_and_process(Worker(repo=repo, settings=settings, process_fn=process_fn), repo)
    assert run.status == RunStatus.FAILED
    assert "crash inatteso" in (run.error_message or "")


def test_process_fn_forgetting_terminal_status_never_leaves_processing(repo, settings) -> None:
    def process_fn(run, repo, settings):
        pass  # non finalizza la run: bug simulato

    _submit(repo)
    run = _claim_and_process(Worker(repo=repo, settings=settings, process_fn=process_fn), repo)
    assert run.status == RunStatus.FAILED
    assert "senza stato terminale" in (run.error_message or "")


def test_start_requeues_stale_processing_runs(repo, settings) -> None:
    _submit(repo)
    stale = repo.claim_next_queued()
    assert stale is not None and stale.status == RunStatus.PROCESSING

    def process_fn(run, repo, settings):
        finalize_run(repo, run.run_id, RunStatus.DONE, run.started_at)

    worker = Worker(repo=repo, settings=settings, process_fn=process_fn)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        current = None
        while time.monotonic() < deadline:
            current = repo.get_run(stale.run_id)
            assert current is not None
            if current.status == RunStatus.DONE:
                break
            time.sleep(0.05)
        assert current.status == RunStatus.DONE
    finally:
        worker.stop()


def test_worker_thread_processes_queued_run_end_to_end(repo, settings) -> None:
    def process_fn(run, repo, settings):
        finalize_run(repo, run.run_id, RunStatus.DONE, run.started_at)

    worker = Worker(repo=repo, settings=settings, process_fn=process_fn)
    worker.start()
    try:
        run = _submit(repo)
        deadline = time.monotonic() + 10
        current = None
        while time.monotonic() < deadline:
            current = repo.get_run(run.run_id)
            assert current is not None
            if current.status not in (RunStatus.QUEUED, RunStatus.PROCESSING):
                break
            time.sleep(0.05)
        assert current.status == RunStatus.DONE
    finally:
        worker.stop()


def test_default_process_fn_delegates_to_pipeline_stub(repo, settings) -> None:
    _submit(repo)
    run = _claim_and_process(Worker(repo=repo, settings=settings), repo)
    assert run.status == RunStatus.FAILED
    assert "non ancora implementata" in (run.error_message or "")
