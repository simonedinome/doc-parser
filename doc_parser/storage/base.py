"""Contratto astratto di persistenza (dati run + file).

Il contratto vale sia per SQLite/filesystem (v1) sia per Table Storage/Blob (v2):
- i metodi file lavorano per riferimento opaco (path locale o URL blob);
- claim_next_queued è atomico: con più worker concorrenti una run Queued
  viene assegnata a un solo chiamante (transazione SQLite in v1, ETag in v2).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal

from doc_parser.core.models import RunRecord, RunStatus

AggregateBy = Literal["run", "session", "user"]


class Repository(ABC):
    @abstractmethod
    def create_run(self, run: RunRecord) -> RunRecord:
        """Persiste una nuova run (tipicamente in stato Queued)."""

    @abstractmethod
    def claim_next_queued(self) -> RunRecord | None:
        """Assegna atomicamente la run Queued più vecchia: la porta in
        Processing con started_at valorizzato e la ritorna; None se la coda
        è vuota o un altro worker ha vinto il claim."""

    @abstractmethod
    def update_run(self, run_id: str, **fields: Any) -> None:
        """Aggiorna i campi indicati della run."""

    @abstractmethod
    def get_run(self, run_id: str) -> RunRecord | None: ...

    @abstractmethod
    def list_runs(
        self,
        requester_upn: str | None = None,
        status: RunStatus | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
    ) -> list[RunRecord]:
        """Run ordinate per created_at decrescente, con filtri opzionali."""

    @abstractmethod
    def aggregate_costs(
        self,
        by: AggregateBy,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Totali per run|session|user: numero run, token e cost_eur."""

    @abstractmethod
    def find_done_by_hash(self, input_hash: str) -> RunRecord | None:
        """Run più recente in stato Done con lo stesso input_hash (dedup)."""

    @abstractmethod
    def save_input_file(self, run_id: str, filename: str, data: bytes) -> str:
        """Salva il file di input e ritorna il riferimento (path/URL)."""

    @abstractmethod
    def save_output_file(self, run_id: str, filename: str, data: bytes) -> str:
        """Salva un file di output e ritorna il riferimento (path/URL)."""

    @abstractmethod
    def get_file(self, ref: str) -> bytes:
        """Legge un file dal riferimento ritornato dai metodi save_*."""
