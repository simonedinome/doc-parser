"""Orchestratore: dal JSON finale costruisce tutti gli artefatti della modalità
"Documentazione operativa" (procedura.txt, glossario.txt, rag_chunks.jsonl,
html, log) e li impacchetta in uno ZIP. Sempre alimentato dal JSON finale
(grezzo se il modello è Gemini, riscritto altrimenti — la distinzione è già
risolta a monte da doc_parser.pipeline.core)."""

from __future__ import annotations

from pathlib import Path

from doc_parser.output.html_builder import build_html_folder, build_html_standalone
from doc_parser.output.logger import Logger, build_log_txt
from doc_parser.output.rag_builder import build_rag_jsonl
from doc_parser.output.txt_builder import build_glossario, build_procedura
from doc_parser.output.zipper import create_zip

HTML_FILENAME_FOLDER = "documentazione.html"
HTML_FILENAME_STANDALONE = "documentazione_standalone.html"


def build_artifacts(
    data: dict,
    source_filename: str,
    language: str,
    html_mode: str,
    screenshot_map: dict[tuple[str, int], Path | None],
    log: Logger,
) -> dict[str, bytes]:
    """Ritorna ``{nome_file: contenuto}`` per tutti gli artefatti testuali/HTML."""
    files: dict[str, bytes] = {
        "procedura.txt": build_procedura(data, source_filename, language).encode("utf-8"),
        "glossario.txt": build_glossario(data, language).encode("utf-8"),
        "rag_chunks.jsonl": build_rag_jsonl(data, source_filename).encode("utf-8"),
    }
    if html_mode in ("folder", "both"):
        files[HTML_FILENAME_FOLDER] = build_html_folder(data, screenshot_map, language).encode("utf-8")
    if html_mode in ("standalone", "both"):
        files[HTML_FILENAME_STANDALONE] = build_html_standalone(data, screenshot_map, language).encode(
            "utf-8"
        )
    files["log.txt"] = build_log_txt(log.lines, language).encode("utf-8")
    return files


def build_output_zip(
    data: dict,
    source_filename: str,
    language: str,
    html_mode: str,
    screenshot_map: dict[tuple[str, int], Path | None],
    screenshots_dir: Path | None,
    log: Logger,
) -> tuple[dict[str, bytes], bytes]:
    """Costruisce gli artefatti e lo ZIP che li impacchetta.

    Ritorna (artefatti, zip_bytes).
    """
    files = build_artifacts(data, source_filename, language, html_mode, screenshot_map, log)
    zip_bytes = create_zip(files, screenshots_dir, html_mode)
    return files, zip_bytes
