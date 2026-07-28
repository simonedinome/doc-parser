from unittest.mock import patch

import pytest

from doc_parser.providers.base import PermanentProviderError, TransientProviderError
from doc_parser.providers.retry import with_retry


def test_with_retry_succeeds_first_attempt_without_sleeping() -> None:
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    with patch("doc_parser.providers.retry.time.sleep") as mock_sleep:
        assert with_retry(fn, max_attempts=3, base_delay=5.0) == "ok"
    assert len(calls) == 1
    mock_sleep.assert_not_called()


def test_with_retry_succeeds_after_transient_failures() -> None:
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TransientProviderError("momentaneamente non disponibile")
        return "ok"

    with patch("doc_parser.providers.retry.time.sleep") as mock_sleep:
        result = with_retry(fn, max_attempts=3, base_delay=5.0)

    assert result == "ok"
    assert attempts["n"] == 3
    # backoff lineare: 5s dopo il 1o tentativo, 10s dopo il 2o
    assert [call.args[0] for call in mock_sleep.call_args_list] == [5.0, 10.0]


def test_with_retry_raises_last_error_after_exhausting_attempts() -> None:
    def fn():
        raise TransientProviderError("sempre non disponibile")

    with patch("doc_parser.providers.retry.time.sleep"):
        with pytest.raises(TransientProviderError, match="sempre non disponibile"):
            with_retry(fn, max_attempts=3, base_delay=1.0)


def test_with_retry_does_not_retry_permanent_errors() -> None:
    calls = []

    def fn():
        calls.append(1)
        raise PermanentProviderError("richiesta non valida")

    with patch("doc_parser.providers.retry.time.sleep") as mock_sleep:
        with pytest.raises(PermanentProviderError):
            with_retry(fn, max_attempts=3, base_delay=1.0)

    assert len(calls) == 1  # nessun retry consumato
    mock_sleep.assert_not_called()
