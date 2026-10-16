"""Orchestratore: dal JSON finale costruisce tutti gli artefatti della modalità
"Documentazione operativa" (procedura.txt, glossario.txt, rag_chunks.jsonl,
html, log) e li impacchetta in uno ZIP. Sempre alimentato dal JSON finale
(grezzo se il modello è Gemini, riscritto altrimenti — la distinzione è già
risolta a monte da doc_parser.pipeline.core)."""

from __future__ import annotations

from pathlib import Path

from doc_parser.output.html_builder import build_html_folder, build_html_standalone
from doc_parser.output.logger import Logger, build_log_txt
from doc_parser.output.pptx_builder import build_pptx
from doc_parser.output.rag_builder import build_rag_jsonl
from doc_parser.output.txt_builder import build_glossario, build_procedura
from doc_parser.output.zipper import create_zip

HTML_FILENAME_FOLDER = "documentazione.html"
HTML_FILENAME_STANDALONE = "documentazione_standalone.html"
PPTX_FILENAME = "presentazione_tutorial.pptx"


def build_artifacts(
    data: dict,
    source_filename: str,
    language: str,
    output_artifacts: list[str],
    screenshot_map: dict[tuple[str, int], Path | None],
    log: Logger,
    slide_map: dict[tuple[str, int], Path] | None = None,
    concept_image_map: dict[str, Path] | None = None,
) -> dict[str, bytes]:
    """Ritorna ``{nome_file: contenuto}`` solo per gli artefatti selezionati
    dall'utente in ``output_artifacts`` (chiavi: ``procedura``, ``glossario``,
    ``rag_chunks``, ``html_standalone``, ``html_folder``, ``pptx``)."""
    files: dict[str, bytes] = {}
    if "procedura" in output_artifacts:
        files["procedura.txt"] = build_procedura(data, source_filename, language).encode("utf-8")
    if "glossario" in output_artifacts:
        files["glossario.txt"] = build_glossario(data, language).encode("utf-8")
    if "rag_chunks" in output_artifacts:
        files["rag_chunks.jsonl"] = build_rag_jsonl(data, source_filename).encode("utf-8")
    if "html_folder" in output_artifacts:
        files[HTML_FILENAME_FOLDER] = build_html_folder(
            data, screenshot_map, language, slide_map, concept_image_map
        ).encode("utf-8")
    if "html_standalone" in output_artifacts:
        files[HTML_FILENAME_STANDALONE] = build_html_standalone(
            data, screenshot_map, language, slide_map, concept_image_map
        ).encode("utf-8")
    if "pptx" in output_artifacts:
        files[PPTX_FILENAME] = build_pptx(data, screenshot_map, concept_image_map, language)
    files["log.txt"] = build_log_txt(log.lines, language).encode("utf-8")
    return files


def build_output_zip(
    data: dict,
    source_filename: str,
    language: str,
    output_artifacts: list[str],
    screenshot_map: dict[tuple[str, int], Path | None],
    screenshots_dir: Path | None,
    log: Logger,
    slide_map: dict[tuple[str, int], Path] | None = None,
    concept_image_map: dict[str, Path] | None = None,
) -> tuple[dict[str, bytes], bytes]:
    """Costruisce gli artefatti e lo ZIP che li impacchetta.

    Ritorna (artefatti, zip_bytes).
    """
    files = build_artifacts(
        data, source_filename, language, output_artifacts, screenshot_map, log, slide_map, concept_image_map
    )
    zip_bytes = create_zip(files, screenshots_dir, output_artifacts)
    return files, zip_bytes
