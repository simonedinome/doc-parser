"""Input delle run video consolidate: descrittori del manifest e loader.

Una run video può ricevere più video, ciascuno etichettato webinar o pillola
con data di registrazione facoltativa, più al massimo un PDF di slide. I
metadati viaggiano nel manifest della run (``input_manifest_ref``); i manifest
scritti prima di questa funzionalità non li hanno e ricevono i default:
``role`` dall'estensione, ``kind`` = webinar, ``input_id`` in ordine (v1, v2…).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime

from doc_parser.core.models import RunRecord
from doc_parser.ingestion.guardrails import classify_extension
from doc_parser.storage.base import Repository

VIDEO_KINDS = ("webinar", "pillola")
DEFAULT_KIND = "webinar"
SLIDES_INPUT_ID = "pdf"

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class InputFile:
    filename: str
    data: bytes
    input_id: str
    role: str  # "video" | "slides"
    kind: str | None = None  # "webinar" | "pillola", solo per i video
    recorded_at: str | None = None  # data ISO (YYYY-MM-DD), solo per i video


def role_for(filename: str) -> str:
    return "slides" if classify_extension(filename) == "pdf" else "video"


def normalize_kind(kind: str | None) -> str:
    if kind is None or kind == "":
        return DEFAULT_KIND
    if kind not in VIDEO_KINDS:
        raise ValueError(f"Tipo di video non valido: {kind!r} (atteso uno tra {', '.join(VIDEO_KINDS)})")
    return kind


def normalize_recorded_at(value: str | date | None) -> str | None:
    """Data di registrazione in formato ISO, None se assente.

    Accetta ``date`` (lo YAML converte le date non quotate) e stringhe
    ``YYYY-MM-DD``; rifiuta orari e altri formati.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        raise ValueError(f"Data di registrazione non valida: {value!r} (attesa una data senza orario, AAAA-MM-GG)")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not _ISO_DATE.match(text):
        raise ValueError(f"Data di registrazione non valida: {value!r} (atteso il formato AAAA-MM-GG)")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"Data di registrazione non valida: {value!r} ({exc})") from exc


def describe_inputs(items: list[tuple[str, str | None, str | date | None]]) -> list[dict]:
    """Descrittori di manifest (senza ``path_ref``) per una run video.

    *items* è ``[(filename, kind, recorded_at)]`` in ordine di caricamento:
    i video ricevono ``v1``, ``v2``… in quell'ordine, il PDF di slide ``pdf``.
    """
    descriptors: list[dict] = []
    video_index = 0
    for filename, kind, recorded_at in items:
        if role_for(filename) == "slides":
            descriptors.append({"filename": filename, "input_id": SLIDES_INPUT_ID, "role": "slides"})
            continue
        video_index += 1
        descriptors.append(
            {
                "filename": filename,
                "input_id": f"v{video_index}",
                "role": "video",
                "kind": normalize_kind(kind),
                "recorded_at": normalize_recorded_at(recorded_at),
            }
        )
    return descriptors


def save_manifest(repo: Repository, run_id: str, descriptors: list[dict], datas: list[bytes]) -> str:
    """Salva i file di input e il manifest; ritorna il riferimento del manifest.

    Ogni file è salvato come ``{input_id}_{filename}``, così due input con lo
    stesso nome (frequente con gli URL) non si sovrascrivono; nel manifest
    resta il nome originale.
    """
    manifest = []
    for descriptor, data in zip(descriptors, datas, strict=True):
        stored_name = f"{descriptor['input_id']}_{descriptor['filename']}"
        manifest.append({**descriptor, "path_ref": repo.save_input_file(run_id, stored_name, data)})
    return repo.save_input_file(run_id, "manifest.json", json.dumps(manifest, ensure_ascii=False).encode("utf-8"))


def load_inputs(run: RunRecord, repo: Repository, preloaded: list[bytes] | None = None) -> list[InputFile]:
    """Carica gli input della run con i metadati, applicando i default di
    retrocompatibilità ai manifest che non li hanno.

    *preloaded*: contenuti già letti, nello stesso ordine del manifest, per
    non tenere due volte in memoria video di grandi dimensioni.
    """
    if run.input_manifest_ref:
        entries = json.loads(repo.get_file(run.input_manifest_ref).decode("utf-8"))
    elif run.input_path:
        entries = [{"filename": run.input_filename, "path_ref": run.input_path}]
    else:
        return []

    inputs: list[InputFile] = []
    video_index = 0
    for position, entry in enumerate(entries):
        filename = entry["filename"]
        data = preloaded[position] if preloaded is not None else repo.get_file(entry["path_ref"])
        role = entry.get("role") or role_for(filename)
        if role == "slides":
            inputs.append(InputFile(filename, data, entry.get("input_id") or SLIDES_INPUT_ID, "slides"))
            continue
        video_index += 1
        inputs.append(
            InputFile(
                filename=filename,
                data=data,
                input_id=entry.get("input_id") or f"v{video_index}",
                role="video",
                kind=entry.get("kind") or DEFAULT_KIND,
                recorded_at=entry.get("recorded_at"),
            )
        )
    return inputs
