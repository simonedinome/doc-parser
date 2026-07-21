"""Provider OpenRouter (chat completions, compatibile OpenAI): PDF, immagini, testo.

I PDF vengono allegati come blocco ``type: "file"`` con il plugin
``file-parser`` (engine ``native``), che delega l'estrazione al provider
upstream (Claude/GPT) invece di rasterizzare le pagine.
"""

from __future__ import annotations

import base64

from openai import APIError, APIStatusError, OpenAI

from doc_parser.providers.base import (
    Attachment,
    BaseProvider,
    PermanentProviderError,
    TransientProviderError,
)
from doc_parser.providers.retry import with_retry

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
_INSUFFICIENT_BALANCE_STATUS_CODE = 402
_INSUFFICIENT_BALANCE_MESSAGE = (
    "Saldo OpenRouter insufficiente per completare la richiesta (HTTP 402): per "
    'l\'elaborazione di file nativi (plugin "file-parser") sono necessari almeno '
    "$0.50 di credito residuo sul tuo account OpenRouter. Ricarica il credito su "
    "https://openrouter.ai/credits e riprova."
)


class OpenRouterProvider(BaseProvider):
    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str,
        max_retries: int = 3,
        retry_backoff_seconds: float = 5.0,
    ) -> None:
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY mancante: configurala nel file .env")
        self._client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
        self._model = model
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        attachments: list[Attachment] | None = None,
    ) -> tuple[str, int, int]:
        attachments = attachments or []
        content: list[dict] = [self._content_block(a) for a in attachments]
        content.append({"type": "text", "text": user_prompt})

        needs_file_plugin = any(a.mime_type == "application/pdf" for a in attachments)
        extra_body = (
            {"plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}]}
            if needs_file_plugin
            else None
        )

        response = with_retry(
            lambda: self._create(content, system_prompt, extra_body),
            max_attempts=self._max_retries,
            base_delay=self._retry_backoff_seconds,
        )

        raw = response.choices[0].message.content or ""
        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        return raw, tokens_in, tokens_out

    def _create(self, content: list[dict], system_prompt: str, extra_body: dict | None):
        try:
            return self._client.chat.completions.create(
                model=self._model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                extra_body=extra_body,
            )
        except APIStatusError as exc:
            if exc.status_code in _TRANSIENT_STATUS_CODES:
                raise TransientProviderError(str(exc)) from exc
            if exc.status_code == _INSUFFICIENT_BALANCE_STATUS_CODE:
                raise PermanentProviderError(
                    f"{_INSUFFICIENT_BALANCE_MESSAGE}\n\nDettaglio tecnico: {exc}"
                ) from exc
            raise PermanentProviderError(str(exc)) from exc
        except APIError as exc:
            raise TransientProviderError(str(exc)) from exc

    @staticmethod
    def _content_block(attachment: Attachment) -> dict:
        data_b64 = base64.b64encode(attachment.data).decode()
        if attachment.mime_type == "application/pdf":
            return {
                "type": "file",
                "file": {
                    "filename": attachment.filename or "documento.pdf",
                    "file_data": f"data:{attachment.mime_type};base64,{data_b64}",
                },
            }
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{attachment.mime_type};base64,{data_b64}"},
        }
