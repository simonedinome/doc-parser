"""Eccezioni di dominio condivise da ingestion, pipeline e worker."""

from __future__ import annotations


class GuardrailRejection(Exception):
    """Input rifiutato prima della chiamata LLM: formato non valido, cifrato,
    oltre soglia dimensione/pagine, URL irraggiungibile o non supportato."""
