"""Worker in background: claim delle run Queued, delega alla pipeline condivisa.

L'elaborazione avviene sempre fuori dalla richiesta Streamlit: la UI scrive
run Queued e legge lo stato; una run sopravvive alla chiusura del tab.

La logica di parsing/guardrail/dedup/builder vive nella pipeline condivisa
(doc_parser.pipeline), non nel worker: CLI e UI Streamlit invocano lo stesso
motore. Il worker si occupa solo di coda, retry di sistema e stato terminale.
"""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime
from typing import Callable

from doc_parser.core.errors import GuardrailRejection
from doc_parser.core.models import RunRecord, RunStatus, utcnow
from doc_parser.settings import Settings
from doc_parser.storage.base import Repository

logger = logging.getLogger(__name__)

ProcessFn = Callable[[RunRecord, Repository, Settings], None]

__all__ = ["GuardrailRejection", "Worker", "finalize_run"]


def finalize_run(
    repo: Repository,
    run_id: str,
    status: RunStatus,
    started_at: datetime | None,
    error_message: str | None = None,
) -> None:
    completed_at = utcnow()
    duration_ms = None
    if started_at is not None:
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
    fields: dict = {
        "status": status,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
    }
    if error_message is not None:
        fields["error_message"] = error_message
    repo.update_run(run_id, **fields)


class Worker:
    def __init__(
        self,
        repo: Repository,
        settings: Settings,
        process_fn: ProcessFn | None = None,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._process_fn = process_fn or _default_process_fn
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # --- Ciclo di vita ---

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._recover_stale_processing()
        self._thread = threading.Thread(target=self._loop, name="doc-parser-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _recover_stale_processing(self) -> None:
        """Run rimaste Processing da un'esecuzione precedente: rimesse in coda."""
        for run in self._repo.list_runs(status=RunStatus.PROCESSING, limit=1000):
            self._repo.update_run(
                run.run_id,
                status=RunStatus.QUEUED,
                started_at=None,
                error_message="Riaccodata dopo interruzione del worker",
            )

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            run = self._repo.claim_next_queued()
            if run is None:
                self._stop_event.wait(self._settings.worker_poll_seconds)
                continue
            self.process_run(run)

    # --- Elaborazione di una run ---

    def process_run(self, run: RunRecord) -> None:
        """Porta una run claimata (Processing) a uno stato terminale.

        Il finally garantisce che nessuna run resti in Processing.
        """
        started_at = run.started_at or utcnow()
        try:
            self._process_fn(run, self._repo, self._settings)
        except GuardrailRejection as exc:
            finalize_run(self._repo, run.run_id, RunStatus.REJECTED, started_at, str(exc))
        except Exception as exc:
            logger.error("Run %s fallita: %s\n%s", run.run_id, exc, traceback.format_exc())
            finalize_run(self._repo, run.run_id, RunStatus.FAILED, started_at, _truncate(str(exc)))
        finally:
            current = self._repo.get_run(run.run_id)
            if current is not None and current.status == RunStatus.PROCESSING:
                finalize_run(
                    self._repo,
                    run.run_id,
                    RunStatus.FAILED,
                    started_at,
                    "Elaborazione interrotta senza stato terminale",
                )


def _default_process_fn(run: RunRecord, repo: Repository, settings: Settings) -> None:
    from doc_parser.pipeline.core import process_run

    process_run(run, repo, settings)


def _truncate(message: str, limit: int = 2000) -> str:
    return message if len(message) <= limit else message[: limit - 1] + "…"
