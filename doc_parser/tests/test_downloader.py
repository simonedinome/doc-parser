from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from doc_parser.core.errors import GuardrailRejection
from doc_parser.ingestion.downloader import download_url


def _fake_response(content_type: str, body: bytes = b"dati", disposition: str | None = None):
    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    resp.raise_for_status.return_value = None
    resp.headers = {"Content-Type": content_type}
    if disposition:
        resp.headers["Content-Disposition"] = disposition
    resp.iter_content.return_value = [body]
    return resp


def test_download_video_uses_content_disposition_filename(tmp_path: Path) -> None:
    resp = _fake_response("video/mp4", body=b"video-bytes", disposition='attachment; filename="clip.mp4"')
    with patch("doc_parser.ingestion.downloader.requests.get", return_value=resp):
        path = download_url("https://example.com/x", tmp_path)
    assert path.name == "clip.mp4"
    assert path.read_bytes() == b"video-bytes"


def test_download_falls_back_to_url_filename(tmp_path: Path) -> None:
    resp = _fake_response("application/pdf")
    with patch("doc_parser.ingestion.downloader.requests.get", return_value=resp):
        path = download_url("https://example.com/docs/manuale.pdf", tmp_path)
    assert path.name == "manuale.pdf"


def test_download_accepts_octet_stream(tmp_path: Path) -> None:
    resp = _fake_response("application/octet-stream")
    with patch("doc_parser.ingestion.downloader.requests.get", return_value=resp):
        download_url("https://example.com/file", tmp_path)


def test_download_rejects_unsupported_content_type(tmp_path: Path) -> None:
    resp = _fake_response("application/x-executable")
    with patch("doc_parser.ingestion.downloader.requests.get", return_value=resp):
        with pytest.raises(GuardrailRejection, match="Content-Type non supportato"):
            download_url("https://example.com/x", tmp_path)


def test_download_unreachable_url_is_guardrail_rejection(tmp_path: Path) -> None:
    with patch(
        "doc_parser.ingestion.downloader.requests.get",
        side_effect=requests.ConnectionError("dns fallita"),
    ):
        with pytest.raises(GuardrailRejection, match="non raggiungibile"):
            download_url("https://esempio-inesistente.invalid/x", tmp_path)


def test_download_http_error_is_guardrail_rejection(tmp_path: Path) -> None:
    resp = _fake_response("video/mp4")
    resp.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
    with patch("doc_parser.ingestion.downloader.requests.get", return_value=resp):
        with pytest.raises(GuardrailRejection, match="non raggiungibile"):
            download_url("https://example.com/assente.mp4", tmp_path)
