"""Helper di presentazione per le pagine Streamlit."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from doc_parser.core.models import RunRecord, RunStatus

STATUS_BADGES: dict[RunStatus, str] = {
    RunStatus.QUEUED: "🕓 In coda",
    RunStatus.PROCESSING: "⚙️ In elaborazione",
    RunStatus.DONE: "✅ Completata",
    RunStatus.FAILED: "❌ Fallita",
    RunStatus.REJECTED: "🚫 Rifiutata",
    RunStatus.DUPLICATE: "♻️ Duplicato",
}

ACTIVE = (RunStatus.QUEUED, RunStatus.PROCESSING)


def badge(status: RunStatus) -> str:
    return STATUS_BADGES.get(status, str(status))


def fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def output_name(run: RunRecord) -> str:
    return Path(run.output_path).name if run.output_path else ""


def friendly_row(run: RunRecord) -> dict:
    """Proiezione 'friendly' della run: stessa tabella, sola vista ridotta."""
    return {
        "Richiedente": run.requester_upn,
        "File": run.input_filename,
        "Output": output_name(run),
        "Stato": badge(run.status),
        "Creata": fmt_dt(run.created_at),
        "Completata": fmt_dt(run.completed_at),
    }


def has_active(runs: list[RunRecord]) -> bool:
    return any(run.status in ACTIVE for run in runs)
