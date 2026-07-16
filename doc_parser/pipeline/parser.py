"""Parsing della risposta JSON del modello e normalizzazione a procedures[]."""

from __future__ import annotations

import json
import re

_REQUIRED_KEYS: list[str] = [
    "title",
    "summary",
    "steps",
    "glossary",
    "notes",
    "prerequisites",
]

_REQUIRED_KEYS_WEBINAR: list[str] = [
    "title",
    "summary",
    "procedures",
    "glossary",
    "notes",
    "prerequisites",
]

_REQUIRED_KEYS_HYBRID: list[str] = [
    "title",
    "summary",
    "concepts",
    "procedures",
    "glossary",
    "notes",
    "prerequisites",
]


def load_json_response(raw: str) -> dict:
    """Rimuove i code fence markdown e carica il JSON, senza validare lo schema
    per content_type: usato per risposte già normalizzate a procedures[] (step 2),
    dove la validazione strutturale è delegata a step2_validate.validate_step2_output.
    """
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON non valido nella risposta del modello: {exc}") from exc


def normalize_to_procedures(data: dict) -> dict:
    """Normalizza il formato flat ``steps`` nel formato annidato ``procedures``.

    Se *data* ha ``steps`` ma non ``procedures``, avvolge gli step in un'unica
    procedura. Se ha già ``procedures``, la ritorna invariata: così tutti i
    builder a valle lavorano uniformemente su ``procedures[]``.
    """
    if "procedures" in data:
        return data
    if "steps" in data:
        data = dict(data)
        data["procedures"] = [
            {
                "id": "proc_001",
                "title": data.get("title", ""),
                "steps": data.pop("steps"),
            }
        ]
    return data


def parse_response(raw: str, content_type: str = "screencast") -> dict:
    """Converte l'output grezzo del modello in un dict di documentazione validato.

    Rimuove i code fence markdown, carica il JSON, valida le chiavi
    obbligatorie e normalizza la struttura.

    Solleva ValueError se il JSON non è valido o la struttura non rispetta
    i requisiti (mai output parziale silenzioso).
    """
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    try:
        data: dict = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON non valido nella risposta del modello: {exc}") from exc

    if content_type == "webinar":
        # Normalizza prima: il modello può rispondere con steps[] flat anche se richiesto procedures[]
        data = normalize_to_procedures(data)
        missing = [k for k in _REQUIRED_KEYS_WEBINAR if k not in data]
        if missing:
            raise ValueError(
                f"Chiavi obbligatorie mancanti nella risposta: {', '.join(missing)}"
            )
        if not isinstance(data["procedures"], list) or len(data["procedures"]) == 0:
            preview = cleaned[:500].replace("\n", " ")
            raise ValueError(
                f"La risposta deve contenere almeno una procedura nella lista 'procedures'.\n"
                f"Chiavi trovate: {list(data.keys())}\n"
                f"Risposta (primi 500 char): {preview}"
            )
        for proc in data["procedures"]:
            steps = proc.get("steps", [])
            if not isinstance(steps, list) or len(steps) == 0:
                raise ValueError(
                    f"La procedura '{proc.get('id', '?')}' deve contenere almeno uno step."
                )

    elif content_type == "hybrid":
        missing = [k for k in _REQUIRED_KEYS_HYBRID if k not in data]
        if missing:
            raise ValueError(
                f"Chiavi obbligatorie mancanti nella risposta: {', '.join(missing)}"
            )
        concepts = data.get("concepts", [])
        procedures = data.get("procedures", [])
        if not isinstance(concepts, list):
            data["concepts"] = []
            concepts = []
        if not isinstance(procedures, list):
            data["procedures"] = []
            procedures = []
        if len(concepts) + len(procedures) == 0:
            preview = cleaned[:500].replace("\n", " ")
            raise ValueError(
                f"La risposta hybrid deve contenere almeno un concetto o una procedura.\n"
                f"Risposta (primi 500 char): {preview}"
            )
        for con in data["concepts"]:
            if "embedding_keywords" in con and not isinstance(con["embedding_keywords"], list):
                con["embedding_keywords"] = []
        for proc in data["procedures"]:
            for step in proc.get("steps", []):
                if "embedding_keywords" in step and not isinstance(step["embedding_keywords"], list):
                    step["embedding_keywords"] = []
                if "source_timestamps" in step and not isinstance(step["source_timestamps"], list):
                    step["source_timestamps"] = []
        return data

    else:
        # screencast / doc: valida il formato steps[] originale, poi normalizza
        missing = [k for k in _REQUIRED_KEYS if k not in data]
        if missing:
            raise ValueError(
                f"Chiavi obbligatorie mancanti nella risposta: {', '.join(missing)}"
            )
        if not isinstance(data["steps"], list) or len(data["steps"]) == 0:
            raise ValueError(
                "La risposta deve contenere almeno uno step nella lista 'steps'."
            )
        data = normalize_to_procedures(data)

    for proc in data.get("procedures", []):
        for step in proc.get("steps", []):
            if "embedding_keywords" in step and not isinstance(step["embedding_keywords"], list):
                step["embedding_keywords"] = []
            if "source_timestamps" in step and not isinstance(step["source_timestamps"], list):
                step["source_timestamps"] = []

    return data
