"""Guardrail pre-LLM: whitelist estensioni, limiti dimensione, ispezione PDF, dedup."""

from __future__ import annotations

import hashlib
from pathlib import Path

from doc_parser.core.errors import GuardrailRejection

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt"}
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS

_KIND_BY_EXTENSION = {
    **{ext: "video" for ext in VIDEO_EXTENSIONS},
    **{ext: "image" for ext in IMAGE_EXTENSIONS},
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".txt": "txt",
}


def classify_extension(filename: str) -> str:
    """Ritorna il tipo di contenuto (video|image|pdf|docx|xlsx|csv|txt) dall'estensione.

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
