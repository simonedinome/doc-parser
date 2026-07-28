import pytest

from doc_parser.pipeline import doc_prompts, manuale_prompts, prompts, video_prompts
from doc_parser.pipeline.profiles import resolve_profile_prompts


def test_resolve_screencast_profile() -> None:
    system, user = resolve_profile_prompts("screencast")
    assert system == prompts.SYSTEM_PROMPT
    assert user == prompts.USER_PROMPT


def test_resolve_video_profile() -> None:
    system, user = resolve_profile_prompts("video")
    assert system == video_prompts.VIDEO_SYSTEM_PROMPT
    assert user == video_prompts.VIDEO_USER_PROMPT


def test_resolve_manuale_profile() -> None:
    system, user = resolve_profile_prompts("manuale")
    assert system == manuale_prompts.MANUALE_SYSTEM_PROMPT
    assert user == manuale_prompts.MANUALE_USER_PROMPT


def test_resolve_doc_profile() -> None:
    system, user = resolve_profile_prompts("documento")
    assert system == doc_prompts.DOC_SYSTEM_PROMPT
    assert user == doc_prompts.DOC_USER_PROMPT


def test_resolve_invalid_profile_raises() -> None:
    with pytest.raises(ValueError, match="non valido"):
        resolve_profile_prompts("pdf")
