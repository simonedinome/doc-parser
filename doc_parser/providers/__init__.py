"""Factory dei provider LLM, risolta dal backend del modello in models.yaml."""

from __future__ import annotations

from doc_parser.core.pricing import get_model
from doc_parser.providers.base import BaseProvider
from doc_parser.settings import Settings


def get_provider_for_model(model_id: str, settings: Settings) -> BaseProvider:
    model = get_model(settings.models_file, model_id)
    if model is None:
        raise ValueError(f"Modello sconosciuto: {model_id!r}")

    if model.backend == "gemini":
        from doc_parser.providers.gemini import GeminiProvider

        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=model_id,
            max_retries=settings.retry_max_attempts,
            retry_backoff_seconds=settings.retry_backoff_seconds,
        )
    if model.backend == "openrouter":
        from doc_parser.providers.openrouter import OpenRouterProvider

        return OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            model=model_id,
            max_retries=settings.retry_max_attempts,
            retry_backoff_seconds=settings.retry_backoff_seconds,
        )
    raise ValueError(f"Backend provider non supportato: {model.backend!r}")
