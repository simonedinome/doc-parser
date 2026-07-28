"""Guardrail pre-LLM: whitelist estensioni, limiti dimensione, ispezione PDF, dedup."""

from __future__ import annotations

import hashlib
from pathlib import Path

from doc_parser.core.errors import GuardrailRejection

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".csv", ".txt"}
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS

_KIND_BY_EXTENSION = {
    **{ext: "video" for ext in VIDEO_EXTENSIONS},
    **{ext: "image" for ext in IMAGE_EXTENSIONS},
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".txt": "txt",
}


def classify_extension(filename: str) -> str:
    """Ritorna il tipo di contenuto (video|image|pdf|docx|doc|xlsx|csv|txt) dall'estensione.

    Solleva GuardrailRejection se l'estensione non è supportata.
    """
    ext = Path(filename).suffix.lower()
    kind = _KIND_BY_EXTENSION.get(ext)
    if kind is None:
        raise GuardrailRejection(f"Estensione non supportata: {ext or '(assente)'}")
    return kind


def check_size(size_bytes: int, max_mb: int) -> None:
    max_bytes = max_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise GuardrailRejection(
            f"File di {size_bytes / (1024 * 1024):.1f} MB oltre la soglia di {max_mb} MB"
        )


def inspect_pdf(pdf_bytes: bytes, max_pages: int) -> int:
    """Verifica che il PDF sia apribile, non cifrato ed entro il limite pagine.

    Ritorna il numero di pagine. Solleva GuardrailRejection altrimenti.
    """
    import fitz

    if not pdf_bytes.startswith(b"%PDF-"):
        raise GuardrailRejection("Il file non è un PDF")
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise GuardrailRejection(f"PDF non apribile: {exc}") from exc
    with doc:
        if doc.needs_pass:
            raise GuardrailRejection("PDF cifrato: rimuovere la protezione e ricaricare")
        pages = doc.page_count
    if pages == 0:
        raise GuardrailRejection("PDF con 0 pagine")
    if pages > max_pages:
        raise GuardrailRejection(f"PDF di {pages} pagine oltre la soglia di {max_pages} pagine")
    return pages


def sha256_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_input_type(is_video: bool, filenames: list[str]) -> str:
    """Determina l'input_type di una run da is_video (dedotto dal content_type
    scelto) e dai file forniti. Condivisa da UI e CLI per non duplicare la logica.

    Solleva GuardrailRejection se i file non sono coerenti con la scelta
    (es. un non-video per un content_type video, o un mix di immagini e
    documenti nello stesso caricamento).
    """
    if is_video:
        for fn in filenames:
            kind = classify_extension(fn)
            if kind != "video":
                raise GuardrailRejection(
                    f"'{fn}' non è un video ({kind}): per il tipo di contenuto scelto carica solo video."
                )
        return "video"

    kinds = [classify_extension(fn) for fn in filenames]
    if all(k == "image" for k in kinds):
        return "image"
    if any(k == "image" for k in kinds):
        raise GuardrailRejection("Non è possibile caricare insieme immagini e documenti.")
    if len(filenames) == 1:
        return kinds[0]
    return "document"
