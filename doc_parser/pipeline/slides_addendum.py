"""Addendum ai prompt di step 1 video quando la run ha un PDF di slide.

Non modifica i prompt protetti (pipeline/video_prompts.py): il testo viene
appeso, come fa apply_language_directive, e solo se il PDF è presente. Testo
approvato da Simone il 15/10/2026; la frase sul prefisso in qualunque lingua
(SLIDES_MARKER_RULE) è una proposta da confermare in review.
"""

from __future__ import annotations

from doc_parser.providers.base import Attachment

DISCREPANCY_MARKER = "DISCORDANZA SLIDE:"

SLIDES_SYSTEM_ADDENDUM = """\
Insieme al video ricevi il PDF delle slide della stessa formazione.
Usa le slide solo per rendere esatti nomi di pulsanti, menu, campi, valori e termini che nel video \
sono poco leggibili o pronunciati in modo ambiguo.
Se slide e video riportano informazioni diverse, documenta ciò che mostra il video e segnala la \
differenza nel campo "notes" dello step, iniziando con "DISCORDANZA SLIDE:".
Non creare procedure o step da slide che il video non tratta."""

SLIDES_MARKER_RULE = 'Mantieni il prefisso "DISCORDANZA SLIDE:" esattamente così, in qualunque lingua.'

SLIDES_USER_ADDENDUM = """\
Aggiungi a ogni step il campo "source_slides": array dei numeri di pagina del PDF (da 1) delle slide \
mostrate o direttamente collegate a quello step; array vuoto se nessuna è pertinente."""


def apply_slides_addendum(system_prompt: str, user_prompt: str) -> tuple[str, str]:
    """Appende l'addendum slide ai prompt di step 1 (system e user)."""
    system = f"{system_prompt}\n\n{SLIDES_SYSTEM_ADDENDUM}\n{SLIDES_MARKER_RULE}"
    user = f"{user_prompt}\n\n{SLIDES_USER_ADDENDUM}"
    return system, user


def slides_attachments(filename: str, data: bytes) -> list[Attachment]:
    """Allegati che rappresentano il PDF di slide nelle chiamate LLM.

    Unico punto da cambiare se il provider rifiuta video e PDF nella stessa
    chiamata (ripiego previsto dal piano: pagine renderizzate come PNG).
    """
    return [Attachment(data=data, mime_type="application/pdf", filename=filename)]
