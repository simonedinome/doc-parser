"""Direttiva di lingua appesa ai prompt esistenti (parametro), non riscrittura dei prompt."""

from __future__ import annotations

_DIRECTIVES = {
    "it": "Scrivi l'intera documentazione in italiano.",
    "en": "Write the entire documentation in English, including every field value in the JSON output.",
}


def apply_language_directive(system_prompt: str, language: str) -> str:
    directive = _DIRECTIVES.get(language)
    if directive is None:
        raise ValueError(f"Lingua non supportata: {language!r}")
    return f"{system_prompt}\n\n{directive}"
