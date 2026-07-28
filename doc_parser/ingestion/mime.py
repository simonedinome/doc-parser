"""Mappa estensione -> MIME type per gli allegati inviati ai provider."""

from __future__ import annotations

from pathlib import Path

_MIME_BY_EXTENSION = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def mime_type_for(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return _MIME_BY_EXTENSION.get(ext, "application/octet-stream")
