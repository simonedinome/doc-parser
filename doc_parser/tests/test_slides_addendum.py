from doc_parser.pipeline.core import _step1_request
from doc_parser.pipeline.inputs import InputFile
from doc_parser.pipeline.language import apply_language_directive
from doc_parser.pipeline.slides_addendum import (
    SLIDES_SYSTEM_ADDENDUM,
    SLIDES_USER_ADDENDUM,
    apply_slides_addendum,
)
from doc_parser.pipeline.video_prompts import VIDEO_SYSTEM_PROMPT, VIDEO_USER_PROMPT

_VIDEO = InputFile("webinar.mp4", b"video", "v1", "video", "webinar", "2026-06-03")
_SLIDES = InputFile("deck.pdf", b"%PDF-", "pdf", "slides")


def test_apply_slides_addendum_appends_without_touching_protected_prompts() -> None:
    system, user = apply_slides_addendum(VIDEO_SYSTEM_PROMPT, VIDEO_USER_PROMPT)
    assert system.startswith(VIDEO_SYSTEM_PROMPT)
    assert user.startswith(VIDEO_USER_PROMPT)
    assert SLIDES_SYSTEM_ADDENDUM in system
    assert SLIDES_USER_ADDENDUM in user


def test_step1_request_with_slides_has_video_and_pdf_and_addendum() -> None:
    system, user, attachments = _step1_request("video", "it", _VIDEO, _SLIDES)

    assert [a.mime_type for a in attachments] == ["video/mp4", "application/pdf"]
    assert [a.data for a in attachments] == [b"video", b"%PDF-"]
    assert system.startswith(VIDEO_SYSTEM_PROMPT)
    assert SLIDES_SYSTEM_ADDENDUM in system
    assert system.endswith(apply_language_directive("", "it").strip())  # lingua sempre ultima
    assert "source_slides" in user


def test_step1_request_without_slides_has_no_addendum() -> None:
    system, user, attachments = _step1_request("video", "en", _VIDEO, None)

    assert len(attachments) == 1
    assert system == apply_language_directive(VIDEO_SYSTEM_PROMPT, "en")
    assert user == VIDEO_USER_PROMPT
    assert "source_slides" not in user
