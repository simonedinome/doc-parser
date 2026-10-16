"""CLI batch: modalità cartella/URL (--input-dir/--urls-file) e coda YAML
(--runs-file), entrambe sullo stesso motore condiviso con la UI Streamlit.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from doc_parser.cli.config import GlobalSettings, InputSource, RunConfig, RunsConfig
from doc_parser.cli.queue_runner import run_queue, run_yaml_queue
from doc_parser.core.errors import GuardrailRejection
from doc_parser.core.models import RunRecord, RunStatus, utcnow
from doc_parser.core.pricing import get_model
from doc_parser.ingestion.guardrails import SUPPORTED_EXTENSIONS
from doc_parser.pipeline.profiles import CONTENT_TYPES
from doc_parser.settings import Settings, get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Default del percorso batch: con i flag a None si distingue un valore passato
# da uno implicito, che serve a --resume (eredita dalla run madre).
BATCH_DEFAULTS = {
    "content_type": "video",
    "model": "anthropic/claude-haiku-4.5",
    "language": "it",
    "output_mode": "documentazione",
    "output_artifacts": "html_standalone,procedura,glossario,rag_chunks",
    "parallel": 3,
    "requester": "cli@local",
}


def _batch_value(args: argparse.Namespace, name: str):
    value = getattr(args, name)
    return BATCH_DEFAULTS[name] if value is None else value


def _list_input_files(input_dir: Path) -> list[Path]:
    return sorted(
        p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _load_urls(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def _build_batch_config(args: argparse.Namespace) -> RunsConfig:
    global_settings = GlobalSettings(
        content_type=_batch_value(args, "content_type"),
        model_id=_batch_value(args, "model"),
        language=_batch_value(args, "language"),
        output_mode=_batch_value(args, "output_mode"),
        output_artifacts=_batch_value(args, "output_artifacts"),
        parallel_runs=_batch_value(args, "parallel"),
        requester_upn=_batch_value(args, "requester"),
    )

    runs: list[RunConfig] = []
    input_dir = Path(args.input_dir) if args.input_dir else None
    if input_dir is not None:
        input_dir.mkdir(parents=True, exist_ok=True)
        for path in _list_input_files(input_dir):
            runs.append(
                RunConfig(name=path.stem, inputs=[InputSource(source="file", path=str(path))])
            )

    if args.urls_file:
        urls_file = Path(args.urls_file)
        if not urls_file.exists():
            raise SystemExit(f"--urls-file non trovato: {urls_file}")
        for url in _load_urls(urls_file):
            name = url.rstrip("/").split("/")[-1] or url
            runs.append(RunConfig(name=name, inputs=[InputSource(source="url", url=url)]))

    return RunsConfig(settings=global_settings, runs=runs)


def build_parser() -> argparse.ArgumentParser:
    d = BATCH_DEFAULTS
    parser = argparse.ArgumentParser(description="doc-parser batch CLI")
    parser.add_argument("--runs-file", metavar="PATH", help="Coda YAML di run da eseguire")
    parser.add_argument("--input-dir", metavar="PATH", help="Cartella con i file da processare")
    parser.add_argument(
        "--urls-file", metavar="PATH", help="File .txt con un URL per riga (righe con # ignorate)"
    )
    parser.add_argument(
        "--resume",
        metavar="RUN_ID",
        help=(
            "Riprende una run video consolidata FALLITA riusando i suoi step 1 salvati: rifà solo "
            "consolidamento e step 2. Eredita input, tipo di contenuto, lingua e modalità di output; "
            "--model e --output-artifacts possono cambiare. Esclusivo con --runs-file/--input-dir/--urls-file"
        ),
    )
    parser.add_argument(
        "--content-type", choices=CONTENT_TYPES,
        help=f"Tipo di contenuto (batch, default: {d['content_type']}; con --resume: quello della run madre)",
    )
    parser.add_argument(
        "--model",
        help=f"ID modello da models.yaml (batch, default: {d['model']}; con --resume: quello della run madre)",
    )
    parser.add_argument(
        "--language", choices=["it", "en"],
        help=f"Lingua dell'output (batch, default: {d['language']}; con --resume: quella della run madre)",
    )
    parser.add_argument(
        "--output-mode", choices=["documentazione", "kb_densa"],
        help=f"Modalità di output (batch, default: {d['output_mode']}; con --resume: quella della run madre)",
    )
    parser.add_argument(
        "--output-artifacts",
        help=(
            "Lista separata da virgole tra: html_standalone, html_folder, procedura, glossario, "
            f"rag_chunks, pptx (pptx solo per le run video). Batch, default: {d['output_artifacts']}; "
            "con --resume: quelli della run madre"
        ),
    )
    parser.add_argument(
        "--parallel", type=int, help=f"Run in parallelo (solo batch, default: {d['parallel']})"
    )
    parser.add_argument(
        "--requester", help=f"requester_upn associato alle run create (solo batch, default: {d['requester']})"
    )
    parser.add_argument("--data-dir", metavar="PATH", help="Override di DATA_DIR (valido anche con --resume)")
    return parser


def main(argv: list[str] | None = None, settings: Settings | None = None) -> RunRecord | None:
    args = build_parser().parse_args(argv)

    settings = settings or get_settings()
    if args.data_dir:
        settings = settings.model_copy(update={"data_dir": Path(args.data_dir)})

    if args.resume:
        return _resume(args, settings)

    if args.runs_file:
        checkpoint = run_yaml_queue(Path(args.runs_file), settings)
    else:
        if not args.input_dir and not args.urls_file:
            raise SystemExit("Specifica --runs-file, oppure --input-dir e/o --urls-file, oppure --resume.")
        config = _build_batch_config(args)
        if not config.runs:
            logger.info("Nessun file o URL da elaborare.")
            return None
        checkpoint = run_queue(config, settings)

    completed = len(checkpoint.get("completed_runs", []))
    failed = checkpoint.get("failed_runs", {})
    logger.info("Completate: %d, Fallite: %d", completed, len(failed))
    for name, error in failed.items():
        logger.error("  %s: %s", name, error)
    return None


def _resume(args: argparse.Namespace, settings: Settings) -> RunRecord:
    """Crea ed esegue la run che riprende args.resume; esce con codice 1 se
    la ripresa non arriva a DONE."""
    from doc_parser.pipeline.core import resume_run_record, validate_resume
    from doc_parser.storage.sqlite_repo import SqliteRepository
    from doc_parser.worker.processor import Worker

    conflicting = [flag for flag, value in (("--runs-file", args.runs_file), ("--input-dir", args.input_dir), ("--urls-file", args.urls_file)) if value]
    if conflicting:
        raise SystemExit(f"--resume non si combina con {', '.join(conflicting)}.")
    for flag, value in (("--requester", args.requester), ("--parallel", args.parallel)):
        if value is not None:
            raise SystemExit(f"{flag} non applicabile con --resume: richiedente e sessione vengono dalla run madre.")

    repo = SqliteRepository(data_dir=settings.data_dir)
    mother = repo.get_run(args.resume)
    if mother is None:
        raise SystemExit(f"--resume: run {args.resume!r} non trovata in {settings.data_dir}.")
    for flag, value, inherited in (
        ("--language", args.language, mother.language),
        ("--content-type", args.content_type, mother.content_type),
        ("--output-mode", args.output_mode, mother.output_mode),
    ):
        if value is not None and value != inherited:
            raise SystemExit(
                f"{flag} {value} è diverso da quello della run da riprendere ({inherited}): con --resume "
                "lingua, tipo di contenuto e modalità di output restano quelli della run madre."
            )
    if args.model and get_model(settings.models_file, args.model) is None:
        raise SystemExit(f"--model {args.model!r} non presente in models.yaml.")

    child = resume_run_record(mother, model_id=args.model, output_artifacts=args.output_artifacts)
    try:
        validate_resume(child, repo)
    except GuardrailRejection as exc:
        raise SystemExit(f"--resume: {exc}") from exc

    # In PROCESSING subito: il worker della UI sullo stesso DB non deve prenderla in carico.
    child.status = RunStatus.PROCESSING
    child.started_at = utcnow()
    repo.create_run(child)
    logger.info("Ripresa della run %s come run %s (modello %s).", mother.run_id[:8], child.run_id[:8], child.model_id)
    Worker(repo=repo, settings=settings).process_run(child)

    result = repo.get_run(child.run_id)
    costs = ", ".join(
        f"{label} {value:.4f} EUR"
        for label, value in (
            ("step 1", result.step1_cost_eur),
            ("consolidamento", result.consolidation_cost_eur),
            ("step 2", result.step2_cost_eur),
        )
        if value is not None
    )
    logger.info("Run %s: %s. Costo totale %.4f EUR (%s).", result.run_id[:8], result.status.value, result.cost_eur or 0.0, costs)
    if result.status != RunStatus.DONE:
        logger.error("Ripresa non completata: %s", result.error_message)
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    main()
