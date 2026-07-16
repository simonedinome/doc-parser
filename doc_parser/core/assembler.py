"""Parsing della risposta JSON del modello e assemblaggio del TXT finale (KB densa)."""

from __future__ import annotations

import json
import re
from datetime import datetime

from doc_parser.core.models import Chunk

UNCERTAINTY_MARKER = "[!] INCERTEZZA: contenuto interpretato con possibile imprecisione"
_SECTION_SEPARATOR = "-" * 80
_HEADER_BORDER = "=" * 80


class ModelResponseError(ValueError):
    """La risposta del modello non è un JSON a chunk valido."""


def extract_chunks(raw: str) -> list[Chunk]:
    """Estrae i chunk dalla risposta grezza del modello.

    Tollera i code fence markdown; solleva ModelResponseError per JSON
    non valido o troncato e per strutture prive di chunk.
    """
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        preview = cleaned[:300].replace("\n", " ")
        raise ModelResponseError(
            f"JSON non valido o troncato nella risposta del modello: {exc}. "
            f"Inizio risposta: {preview}"
        ) from exc

    if not isinstance(data, dict) or not isinstance(data.get("chunks"), list):
        raise ModelResponseError(
            "La risposta del modello non contiene la lista 'chunks'."
        )
    if len(data["chunks"]) == 0:
        raise ModelResponseError("La risposta del modello contiene zero chunk.")

    chunks: list[Chunk] = []
    for i, item in enumerate(data["chunks"], start=1):
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            raise ModelResponseError(f"Il chunk in posizione {i} è privo di testo.")
        chunks.append(
            Chunk(
                index=int(item.get("index", i)),
                title=str(item.get("title", "") or ""),
                text=str(item["text"]).strip(),
                has_uncertainty=bool(item.get("has_uncertainty", False)),
            )
        )
    return chunks


def count_uncertainty(chunks: list[Chunk]) -> int:
    return sum(1 for c in chunks if c.has_uncertainty)


def assemble_txt(
    chunks: list[Chunk],
    source_filename: str,
    generated_at: datetime,
) -> str:
    """Assembla i chunk nel TXT denso finale per la knowledge base."""
    uncertainty = count_uncertainty(chunks)
    lines = [
        _HEADER_BORDER,
        f"KNOWLEDGE BASE — {source_filename}",
        f"Generato: {generated_at.strftime('%Y-%m-%d %H:%M:%S %Z').strip()}",
        f"Chunk: {len(chunks)} | Segnalazioni di incertezza: {uncertainty}",
        _HEADER_BORDER,
        "",
    ]
    for pos, chunk in enumerate(chunks):
        if pos > 0:
            lines.extend([_SECTION_SEPARATOR, ""])
        title = f" — {chunk.title}" if chunk.title else ""
        lines.append(f"[CHUNK {chunk.index}]{title}")
        if chunk.has_uncertainty:
            lines.append(UNCERTAINTY_MARKER)
        lines.extend(["", chunk.text, ""])
    return "\n".join(lines)
