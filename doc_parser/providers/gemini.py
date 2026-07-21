"""Provider Gemini via API nativa (google-genai): video, PDF, immagini, testo."""

from __future__ import annotations

import shutil
import tempfile
import time
import unicodedata
from pathlib import Path

from google import genai
from google.genai import types as genai_types

from doc_parser.providers.base import (
    Attachment,
    BaseProvider,
    PermanentProviderError,
    TransientProviderError,
)
from doc_parser.providers.retry import with_retry

_UPLOAD_POLL_SECONDS = 2.0
_UPLOAD_TIMEOUT_SECONDS = 300.0
_INLINE_DATA_MAX_BYTES = 20 * 1024 * 1024  # 20 MB: sotto soglia, dati inline invece di Files API
_TRANSIENT_MARKERS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "DEADLINE_EXCEEDED",
)
_AUTH_MARKERS = ("ACCESS_TOKEN_TYPE_UNSUPPORTED", "UNAUTHENTICATED")
_AUTH_ERROR_MESSAGE = (
    "Autenticazione Gemini rifiutata (HTTP 401 ACCESS_TOKEN_TYPE_UNSUPPORTED): le chiavi "
    'API Gemini in formato "AQ." non sono al momento accettate dalla Files API di Google '
    '(necessaria per i file di grandi dimensioni, es. i video), pur funzionando per le '
    "richieste testuali dirette. Verifica il formato della tua GEMINI_API_KEY su "
    "https://aistudio.google.com/apikey: se è \"AQ.\", si tratta di una restrizione nota "
    "lato Google sul tipo di chiave, non di un problema di configurazione dell'app."
)


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        max_retries: int = 3,
        retry_backoff_seconds: float = 5.0,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY mancante: configurala nel file .env")
        self._client = genai.Client(api_key=api_key)
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
        inline_parts = []
        uploaded: list[tuple] = []
        for a in attachments:
            if len(a.data) <= _INLINE_DATA_MAX_BYTES:
                inline_parts.append(genai_types.Part.from_bytes(data=a.data, mime_type=a.mime_type))
            else:
                uploaded.append((self._upload(a), a.mime_type))
        try:
            parts = list(inline_parts) + [
                genai_types.Part.from_uri(file_uri=f.uri, mime_type=mime_type)
                for f, mime_type in uploaded
            ]
            parts.append(genai_types.Part.from_text(text=user_prompt))
            response = with_retry(
                lambda: self._generate_content(parts, system_prompt),
                max_attempts=self._max_retries,
                base_delay=self._retry_backoff_seconds,
            )
        finally:
            for f, _ in uploaded:
                self._delete_quietly(f)

        raw = response.text or ""
        usage = response.usage_metadata
        tokens_in = int(getattr(usage, "prompt_token_count", 0) or 0)
        tokens_out = int(getattr(usage, "candidates_token_count", 0) or 0)
        return raw, tokens_in, tokens_out

    def _generate_content(self, parts: list, system_prompt: str):
        try:
            return self._client.models.generate_content(
                model=self._model,
                contents=genai_types.Content(role="user", parts=parts),
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
        except Exception as exc:
            raise _classify(exc) from exc

    def _upload(self, attachment: Attachment):
        display_name = (
            unicodedata.normalize("NFKD", attachment.filename or "file")
            .encode("ascii", "ignore")
            .decode("ascii")
        ) or "file"

        tmp_dir = Path(tempfile.mkdtemp(prefix="doc_parser_upload_"))
        upload_path = tmp_dir / display_name
        upload_path.write_bytes(attachment.data)
        try:
            uploaded = self._client.files.upload(
                file=upload_path,
                config=genai_types.UploadFileConfig(
                    mime_type=attachment.mime_type,
                    display_name=display_name,
                ),
            )
        except Exception as exc:
            raise _classify(exc) from exc
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        deadline = time.monotonic() + _UPLOAD_TIMEOUT_SECONDS
        try:
            while uploaded.state and uploaded.state.name == "PROCESSING":
                if time.monotonic() > deadline:
                    raise TransientProviderError(
                        "Timeout in attesa che il file caricato diventi ACTIVE"
                    )
                time.sleep(_UPLOAD_POLL_SECONDS)
                uploaded = self._client.files.get(name=uploaded.name)
        except (TransientProviderError, PermanentProviderError):
            raise
        except Exception as exc:
            raise _classify(exc) from exc

        if uploaded.state and uploaded.state.name == "FAILED":
            raise PermanentProviderError("Upload del file fallito lato Gemini Files API")
        return uploaded

    def _delete_quietly(self, uploaded) -> None:
        try:
            if uploaded is not None and uploaded.name:
                self._client.files.delete(name=uploaded.name)
        except Exception:
            pass


def _classify(exc: Exception) -> TransientProviderError | PermanentProviderError:
    message = str(exc)
    if any(marker in message for marker in _TRANSIENT_MARKERS):
        return TransientProviderError(message)
    if any(marker in message for marker in _AUTH_MARKERS):
        return PermanentProviderError(f"{_AUTH_ERROR_MESSAGE}\n\nDettaglio tecnico: {message}")
    return PermanentProviderError(message)
