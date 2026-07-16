"""Download HTTP diretto per l'ingestion da lista URL.

A differenza del downloader originale di video-to-docs (limitato a
Content-Type "video/*"), qui il controllo copre tutti i formati supportati
dall'ingestion (video, PDF, docx/xlsx/csv/txt, immagini), così le run non-
video possono essere alimentate anche da URL e non solo da upload diretto.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from doc_parser.core.errors import GuardrailRejection

_CONTENT_TYPE_PREFIXES = ("video/", "image/")
_CONTENT_TYPE_EXACT = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/plain",
    "application/octet-stream",
}


def download_url(url: str, dest_dir: Path, timeout: int = 120) -> Path:
    """Scarica *url* in *dest_dir* e ritorna il path del file scaricato.

    Solleva GuardrailRejection se l'URL non è raggiungibile o se il
    Content-Type restituito non è tra i formati supportati (i controlli più
    fini sul contenuto effettivo restano ai guardrail per-formato a valle).
    """
    try:
        with requests.get(url, stream=True, timeout=timeout) as response:
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if not (
                content_type.startswith(_CONTENT_TYPE_PREFIXES)
                or content_type in _CONTENT_TYPE_EXACT
            ):
                raise GuardrailRejection(
                    f"Content-Type non supportato: {content_type or '(assente)'}"
                )

            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / _filename_from_headers(response.headers, url)
            with dest_path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                    if chunk:
                        fh.write(chunk)
            return dest_path
    except requests.RequestException as exc:
        raise GuardrailRejection(f"URL non raggiungibile: {exc}") from exc


def _filename_from_headers(headers, url: str) -> str:
    content_disposition = headers.get("Content-Disposition", "")
    if content_disposition:
        for part in content_disposition.split(";"):
            part = part.strip()
            if part.lower().startswith("filename="):
                name = part[len("filename=") :].strip().strip('"').strip("'")
                if name:
                    return Path(name).name

    path_segment = unquote(urlparse(url).path.split("/")[-1])
    return path_segment or "download"
