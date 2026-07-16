"""Punto di ingresso condiviso della pipeline di elaborazione.

Invocato dal worker in background e dalla CLI: guardrail, dedup, parsing
(step 1/2 per i video, step unico per gli altri formati) e generazione degli
artefatti finali vivono qui, cosicché CLI e UI Streamlit condividano lo
stesso motore. Implementato in Fase 4.
"""

from __future__ import annotations

from doc_parser.core.models import RunRecord
from doc_parser.settings import Settings
from doc_parser.storage.base import Repository


def process_run(run: RunRecord, repo: Repository, settings: Settings) -> None:
    raise NotImplementedError("Pipeline di elaborazione non ancora implementata (Fase 4)")
