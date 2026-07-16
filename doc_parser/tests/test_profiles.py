import pytest

from doc_parser.pipeline import doc_prompts, hybrid_prompts, prompts, webinar_prompts
from doc_parser.pipeline.profiles import resolve_profile_prompts


def test_resolve_screencast_profile() -> None:
    system, user = resolve_profile_prompts("screencast")
    assert system == prompts.SYSTEM_PROMPT
    assert user == prompts.USER_PROMPT


def test_resolve_webinar_profile() -> None:
    system, user = resolve_profile_prompts("webinar")
    assert system == webinar_prompts.WEBINAR_SYSTEM_PROMPT
    assert user == webinar_prompts.WEBINAR_USER_PROMPT


def test_resolve_hybrid_profile() -> None:
    system, user = resolve_profile_prompts("hybrid")
    assert system == hybrid_prompts.HYBRID_SYSTEM_PROMPT
    assert user == hybrid_prompts.HYBRID_USER_PROMPT


def test_resolve_doc_profile() -> None:
    system, user = resolve_profile_prompts("doc")
    assert system == doc_prompts.DOC_SYSTEM_PROMPT
    assert user == doc_prompts.DOC_USER_PROMPT


def test_resolve_invalid_profile_raises() -> None:
    with pytest.raises(ValueError, match="non valido"):
        resolve_profile_prompts("pdf")
