"""Contratto generico dei provider LLM.

Un solo metodo, system+user prompt più allegati opzionali, ritorna
(testo grezzo, token input, token output). Usato identicamente per lo step 1
video, lo step 2 di riscrittura e il percorso single-step non-video: la
scelta del prompt e degli allegati resta responsabilità della pipeline
(doc_parser.pipeline), non del provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(Exception):
    """Errore del provider LLM."""


class TransientProviderError(ProviderError):
    """Errore transitorio (rate limit, 5xx, rete): ritentabile."""


class PermanentProviderError(ProviderError):
    """Errore permanente (richiesta non valida, risposta non ottenibile): non ritentabile."""


@dataclass
class Attachment:
    data: bytes
    mime_type: str
    filename: str = ""


class BaseProvider(ABC):
    name: str

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        attachments: list[Attachment] | None = None,
    ) -> tuple[str, int, int]:
        """Ritorna (testo grezzo della risposta, token input, token output)."""
