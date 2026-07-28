"""Helper di presentazione per le pagine Streamlit."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from doc_parser.core.models import RunRecord, RunStatus, utcnow

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


def origin_label(run: RunRecord) -> str:
    return f"Rielaborazione di run #{run.parent_run_id[:8]}" if run.parent_run_id else ""


def download_filename(run: RunRecord) -> str:
    """Nome file proposto in download, più leggibile del ref di storage."""
    stem = Path(run.input_filename).stem if run.input_filename else run.run_id[:8]
    if run.output_mode == "kb_densa":
        return f"{stem}.txt"
    return f"{stem}.zip"


def friendly_row(run: RunRecord) -> dict:
    """Proiezione 'friendly' della run: stessa tabella, sola vista ridotta."""
    return {
        "Richiedente": run.requester_upn,
        "File": run.input_filename,
        "Origine": origin_label(run),
        "Modello": run.model_id or "",
        "Output": output_name(run),
        "Stato": badge(run.status),
        "Costo (EUR)": f"{run.cost_eur:.4f}" if run.cost_eur is not None else "",
        "Costo step1 (EUR)": f"{run.step1_cost_eur:.4f}" if run.step1_cost_eur is not None else "",
        "Costo step2 (EUR)": f"{run.step2_cost_eur:.4f}" if run.step2_cost_eur is not None else "",
        "Creata": fmt_dt(run.created_at),
        "Completata": fmt_dt(run.completed_at),
    }


def has_active(runs: list[RunRecord]) -> bool:
    return any(run.status in ACTIVE for run in runs)


def input_download_entries(repo, run: RunRecord) -> list[tuple[str, str]]:
    """Ritorna ``[(nome_file, ref)]`` per i file di input della run, sia a
    file singolo (``input_path``) sia multi-file (``input_manifest_ref``)."""
    if run.input_manifest_ref:
        manifest = json.loads(repo.get_file(run.input_manifest_ref).decode("utf-8"))
        return [(entry["filename"], entry["path_ref"]) for entry in manifest]
    if run.input_path:
        return [(run.input_filename or Path(run.input_path).name, run.input_path)]
    return []


_COST_WINDOWS = [
    ("Ultime 24 ore", timedelta(hours=24)),
    ("Ultimi 7 giorni", timedelta(days=7)),
    ("Ultimi 28 giorni", timedelta(days=28)),
]


def cost_summary_windows(repo, upn: str | None = None) -> list[tuple[str, list[dict]]]:
    """Riepilogo costi per utente su 3 finestre mobili (24h/7g/28g).

    Ritorna ``[(etichetta_finestra, righe_per_utente)]``, dove ogni riga è
    ``{"group_key": upn, "run_count", "tokens_total", "cost_eur"}`` (stesso
    formato di ``Repository.aggregate_costs``). Se ``upn`` è specificato,
    filtra alla sola riga di quell'utente (per «Le mie richieste»);
    altrimenti ritorna le righe di tutti gli utenti (per «Log»/«Log tecnico»).
    """
    now = utcnow()
    result = []
    for label, delta in _COST_WINDOWS:
        rows = repo.aggregate_costs(by="user", since=now - delta)
        if upn is not None:
            rows = [r for r in rows if r["group_key"] == upn]
        result.append((label, rows))
    return result


def output_artifact_entries(run: RunRecord) -> list[tuple[str, str]]:
    """Ritorna ``[(nome_file, path)]`` per i singoli artefatti di output
    (oltre allo ZIP), letti dalla cartella ``output_dir_ref`` valorizzata
    dalla modalità "documentazione operativa". Vuoto per KB densa (un solo
    file, già scaricabile via ``output_path``)."""
    if not run.output_dir_ref:
        return []
    dir_path = Path(run.output_dir_ref)
    if not dir_path.exists():
        return []
    return sorted((p.name, str(p)) for p in dir_path.iterdir() if p.is_file())
