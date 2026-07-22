"""Retry con backoff lineare per gli errori transitori dei provider LLM."""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

from doc_parser.providers.base import TransientProviderError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 5.0,
) -> T:
    """Chiama *fn* fino a *max_attempts* volte con backoff lineare (5s, 10s, 15s).

    Ritenta solo su TransientProviderError; una PermanentProviderError (o
    qualunque altra eccezione) si propaga immediatamente senza consumare
    tentativi.
    """
    last_exc: TransientProviderError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except TransientProviderError as exc:
            last_exc = exc
            logger.warning("Tentativo %d/%d fallito: %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                delay = base_delay * attempt
                logger.info("Attesa %.1fs prima del prossimo tentativo...", delay)
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]
