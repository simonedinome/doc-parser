from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIStatusError

from doc_parser.providers import get_provider_for_model
from doc_parser.providers.base import (
    Attachment,
    PermanentProviderError,
    TransientProviderError,
)
from doc_parser.providers.gemini import GeminiProvider
from doc_parser.providers.openrouter import OpenRouterProvider
from doc_parser.settings import Settings

_MODELS_FILE = Path(__file__).resolve().parent.parent.parent / "models.yaml"


def _settings(**overrides) -> Settings:
    base = dict(
        gemini_api_key="test-key",
        openrouter_api_key="test-key",
        models_file=_MODELS_FILE,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


# --- Factory ---


def test_factory_resolves_gemini_backend() -> None:
    provider = get_provider_for_model("gemini-2.5-flash-lite", _settings())
    assert isinstance(provider, GeminiProvider)


def test_factory_resolves_openrouter_backend() -> None:
    provider = get_provider_for_model("anthropic/claude-haiku-4.5", _settings())
    assert isinstance(provider, OpenRouterProvider)


def test_factory_unknown_model_raises() -> None:
    with pytest.raises(ValueError, match="sconosciuto"):
        get_provider_for_model("modello-inesistente", _settings())


def test_gemini_requires_api_key() -> None:
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        get_provider_for_model("gemini-2.5-flash-lite", _settings(gemini_api_key=""))


def test_openrouter_requires_api_key() -> None:
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        get_provider_for_model("anthropic/claude-haiku-4.5", _settings(openrouter_api_key=""))


# --- Gemini (mockato) ---


def _fake_gemini_client(response_text: str) -> MagicMock:
    client = MagicMock()
    uploaded = SimpleNamespace(name="files/abc", uri="files/abc", mime_type="application/pdf", state=SimpleNamespace(name="ACTIVE"))
    client.files.upload.return_value = uploaded
    client.models.generate_content.return_value = SimpleNamespace(
        text=response_text,
        usage_metadata=SimpleNamespace(prompt_token_count=1000, candidates_token_count=200),
    )
    return client


def test_gemini_generate_with_attachment_mocked() -> None:
    provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash-lite")
    provider._client = _fake_gemini_client('{"ok": true}')

    raw, tokens_in, tokens_out = provider.generate(
        "system", "user", [Attachment(data=b"%PDF-fake", mime_type="application/pdf", filename="a.pdf")]
    )

    assert raw == '{"ok": true}'
    assert (tokens_in, tokens_out) == (1000, 200)
    provider._client.files.upload.assert_called_once()
    provider._client.files.delete.assert_called_once()


def test_gemini_generate_without_attachments_skips_upload() -> None:
    provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash-lite")
    provider._client = _fake_gemini_client('{"ok": true}')

    provider.generate("system", "user")

    provider._client.files.upload.assert_not_called()


def test_gemini_transient_error_is_classified() -> None:
    provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash-lite")
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("503 UNAVAILABLE")
    provider._client = client
    provider._max_retries = 1

    with pytest.raises(TransientProviderError):
        provider.generate("system", "user")


def test_gemini_permanent_error_is_classified() -> None:
    provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash-lite")
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("richiesta non valida")
    provider._client = client

    with pytest.raises(PermanentProviderError):
        provider.generate("system", "user")


# --- OpenRouter (mockato) ---


def _fake_openrouter_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=500, completion_tokens=100),
    )


def test_openrouter_text_only_generate() -> None:
    provider = OpenRouterProvider(api_key="test-key", model="anthropic/claude-haiku-4.5")
    provider._client = MagicMock()
    provider._client.chat.completions.create.return_value = _fake_openrouter_response("risposta")

    raw, tokens_in, tokens_out = provider.generate("system", "user")

    assert raw == "risposta"
    assert (tokens_in, tokens_out) == (500, 100)
    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] is None
    assert kwargs["messages"][1]["content"] == [{"type": "text", "text": "user"}]


def test_openrouter_pdf_attachment_uses_file_parser_plugin() -> None:
    provider = OpenRouterProvider(api_key="test-key", model="openai/gpt-5.2")
    provider._client = MagicMock()
    provider._client.chat.completions.create.return_value = _fake_openrouter_response("ok")

    provider.generate(
        "system", "user", [Attachment(data=b"%PDF-fake", mime_type="application/pdf", filename="a.pdf")]
    )

    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] == {"plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}]}
    content = kwargs["messages"][1]["content"]
    assert content[0]["type"] == "file"
    assert content[0]["file"]["file_data"].startswith("data:application/pdf;base64,")


def test_openrouter_image_attachment_uses_image_url_block() -> None:
    provider = OpenRouterProvider(api_key="test-key", model="openai/gpt-5.2")
    provider._client = MagicMock()
    provider._client.chat.completions.create.return_value = _fake_openrouter_response("ok")

    provider.generate(
        "system", "user", [Attachment(data=b"\x89PNG", mime_type="image/png", filename="a.png")]
    )

    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] is None
    content = kwargs["messages"][1]["content"]
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_openrouter_rate_limit_is_transient() -> None:
    provider = OpenRouterProvider(api_key="test-key", model="openai/gpt-5.2")
    provider._client = MagicMock()
    provider._client.chat.completions.create.side_effect = APIStatusError(
        "rate limited",
        response=httpx.Response(429, request=httpx.Request("POST", "https://x")),
        body=None,
    )

    with pytest.raises(TransientProviderError):
        provider.generate("system", "user")


def test_openrouter_bad_request_is_permanent() -> None:
    provider = OpenRouterProvider(api_key="test-key", model="openai/gpt-5.2")
    provider._client = MagicMock()
    provider._client.chat.completions.create.side_effect = APIStatusError(
        "richiesta non valida",
        response=httpx.Response(400, request=httpx.Request("POST", "https://x")),
        body=None,
    )

    with pytest.raises(PermanentProviderError):
        provider.generate("system", "user")
