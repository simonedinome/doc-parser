"""FoundryProvider è dormiente in v1 (nessuna voce nel menu utente): questi test
verificano solo che l'implementazione preservata per l'attivazione v2 funzioni.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import openai
import pytest

from doc_parser.core.kb_densa_prompts import PROMPT_VERSION
from doc_parser.providers.base import PermanentProviderError
from doc_parser.providers.foundry import FoundryProvider

CHUNKS_JSON = json.dumps(
    {
        "chunks": [
            {"index": 1, "title": "A", "text": "Primo.", "has_uncertainty": False},
            {"index": 2, "title": "B", "text": "Secondo.", "has_uncertainty": True},
        ]
    }
)


def _sample_pdf(pages: int = 2) -> bytes:
    import fitz

    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Pagina {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def _foundry_provider(pages_per_batch: int = 10) -> FoundryProvider:
    return FoundryProvider(
        endpoint="https://esempio.openai.azure.com",
        api_key="test-key",
        deployment="gpt-4.1-mini",
        pages_per_batch=pages_per_batch,
    )


def _foundry_response(payload: str, tokens_in: int = 500, tokens_out: int = 100):
    return SimpleNamespace(
        output_text=payload,
        usage=SimpleNamespace(input_tokens=tokens_in, output_tokens=tokens_out, total_tokens=tokens_in + tokens_out),
    )


def test_requires_credentials() -> None:
    with pytest.raises(ValueError, match="FOUNDRY_ENDPOINT"):
        FoundryProvider(endpoint="", api_key="x", deployment="d")


def test_direct_pdf() -> None:
    provider = _foundry_provider()
    provider._client = MagicMock()
    provider._client.responses.create.return_value = _foundry_response(CHUNKS_JSON)

    result = provider.parse_pdf(_sample_pdf(), "doc1.pdf")

    assert result.provider == "foundry"
    assert result.model_version == "gpt-4.1-mini"
    assert result.prompt_version == PROMPT_VERSION
    assert result.chunk_count == 2
    assert result.uncertainty_count == 1
    assert provider._direct_pdf_supported is True
    content = provider._client.responses.create.call_args.kwargs["input"][0]["content"]
    assert content[0]["type"] == "input_file"


def test_falls_back_to_raster_on_unsupported_pdf() -> None:
    provider = _foundry_provider(pages_per_batch=1)
    provider._client = MagicMock()
    bad_request = openai.BadRequestError(
        "input_file non supportato",
        response=httpx.Response(400, request=httpx.Request("POST", "https://x")),
        body=None,
    )
    batch1 = json.dumps({"chunks": [{"index": 1, "title": "P1", "text": "Pagina uno."}]})
    batch2 = json.dumps({"chunks": [{"index": 2, "title": "P2", "text": "Pagina due.", "has_uncertainty": True}]})
    provider._client.responses.create.side_effect = [bad_request, _foundry_response(batch1), _foundry_response(batch2)]

    result = provider.parse_pdf(_sample_pdf(pages=2), "doc1.pdf")

    assert provider._direct_pdf_supported is False
    assert result.chunk_count == 2
    assert result.uncertainty_count == 1
    assert result.tokens_in == 1000 and result.tokens_out == 200
    assert provider._client.responses.create.call_count == 3


def test_malformed_response_is_permanent_error() -> None:
    provider = _foundry_provider()
    provider._client = MagicMock()
    provider._client.responses.create.return_value = _foundry_response("non-json")

    with pytest.raises(PermanentProviderError):
        provider.parse_pdf(b"%PDF-fake", "doc1.pdf")
