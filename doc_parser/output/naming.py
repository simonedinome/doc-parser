"""Nomi leggibili per le cartelle di output e per il TXT KB di una run.

Il nome della run viene, in ordine: dal ``name`` della coda YAML (sessione
``cli-<name>``), dal nome del file caricato, dal titolo del documento (le
serie caricate dalla UI si chiamano «N file»). La data e l'ora di avvio
rendono unica ogni versione: rifare una run non sovrascrive quella precedente.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

_CLI_SESSION_PREFIX = "cli-"
_UI_GROUP_PLACEHOLDER = re.compile(r"^\d+ file$")
_GENERIC_NAMES = {"", "run"}
_MAX_SLUG_LENGTH = 60


def slugify(text: str) -> str:
    """Slug ASCII minuscolo con trattini, adatto a nomi di file e cartelle."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:_MAX_SLUG_LENGTH].rstrip("-") or "run"


def run_label(session_id: str | None, source_filename: str | None, title: str | None) -> str:
    """Nome leggibile della run (slug)."""
    if session_id and session_id.startswith(_CLI_SESSION_PREFIX) and len(session_id) > len(_CLI_SESSION_PREFIX):
        return slugify(session_id[len(_CLI_SESSION_PREFIX):])
    filename = (source_filename or "").strip()
    if filename not in _GENERIC_NAMES and not _UI_GROUP_PLACEHOLDER.match(filename):
        return slugify(Path(filename).stem)
    return slugify(title or "run")


def run_timestamp(moment: datetime) -> str:
    """``AAAA-MM-GG_HHMM`` nell'ora locale della macchina che esegue la run."""
    local = moment.astimezone() if moment.tzinfo is not None else moment
    return local.strftime("%Y-%m-%d_%H%M")


def unique_dir(base: Path, name: str) -> Path:
    """``base/name``, oppure ``name_2``, ``name_3``… se esiste già."""
    candidate = base / name
    counter = 2
    while candidate.exists():
        candidate = base / f"{name}_{counter}"
        counter += 1
    return candidate
