"""CLI batch: modalità cartella/URL (--input-dir/--urls-file) e coda YAML
(--runs-file), entrambe sullo stesso motore condiviso con la UI Streamlit.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from doc_parser.cli.config import GlobalSettings, InputSource, RunConfig, RunsConfig
from doc_parser.cli.queue_runner import run_queue, run_yaml_queue
from doc_parser.ingestion.guardrails import SUPPORTED_EXTENSIONS
from doc_parser.pipeline.profiles import CONTENT_TYPES
from doc_parser.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _list_input_files(input_dir: Path) -> list[Path]:
    return sorted(
        p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _load_urls(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def _build_batch_config(args: argparse.Namespace) -> RunsConfig:
    global_settings = GlobalSettings(
        content_type=args.content_type,
        model_id=args.model,
        language=args.language,
        output_mode=args.output_mode,
        output_artifacts=args.output_artifacts,
        parallel_runs=args.parallel,
        requester_upn=args.requester,
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="doc-parser batch CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--runs-file", metavar="PATH", help="Coda YAML di run da eseguire")
    parser.add_argument("--input-dir", metavar="PATH", help="Cartella con i file da processare")
    parser.add_argument(
        "--urls-file", metavar="PATH", help="File .txt con un URL per riga (righe con # ignorate)"
    )
    parser.add_argument("--content-type", default="screencast", choices=CONTENT_TYPES)
    parser.add_argument("--model", default="anthropic/claude-haiku-4.5", help="ID modello da models.yaml")
    parser.add_argument("--language", default="it", choices=["it", "en"])
    parser.add_argument("--output-mode", default="documentazione", choices=["documentazione", "kb_densa"])
    parser.add_argument(
        "--output-artifacts",
        default="html_standalone,procedura,glossario,rag_chunks",
        help=(
            "Lista separata da virgole tra: html_standalone, html_folder, "
            "procedura, glossario, rag_chunks"
        ),
    )
    parser.add_argument("--parallel", type=int, default=3, help="Run in parallelo (solo modalità batch)")
    parser.add_argument("--requester", default="cli@local", help="requester_upn associato alle run create")
    parser.add_argument("--data-dir", metavar="PATH", help="Override di DATA_DIR")
    args = parser.parse_args()

    settings = get_settings()
    if args.data_dir:
        settings = settings.model_copy(update={"data_dir": Path(args.data_dir)})

    if args.runs_file:
        checkpoint = run_yaml_queue(Path(args.runs_file), settings)
    else:
        if not args.input_dir and not args.urls_file:
            raise SystemExit("Specifica --runs-file, oppure --input-dir e/o --urls-file.")
        config = _build_batch_config(args)
        if not config.runs:
            logger.info("Nessun file o URL da elaborare.")
            return
        checkpoint = run_queue(config, settings)

    completed = len(checkpoint.get("completed_runs", []))
    failed = checkpoint.get("failed_runs", {})
    logger.info("Completate: %d, Fallite: %d", completed, len(failed))
    for name, error in failed.items():
        logger.error("  %s: %s", name, error)


if __name__ == "__main__":
    main()
