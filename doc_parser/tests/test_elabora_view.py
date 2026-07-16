import pytest

from doc_parser.ui.views.elabora import _resolve_input_type


def test_video_content_type_requires_all_video_files() -> None:
    assert _resolve_input_type("screencast", True, ["a.mp4", "b.mov"]) == "video"


def test_video_content_type_rejects_non_video_file() -> None:
    with pytest.raises(ValueError, match="non è un video"):
        _resolve_input_type("screencast", True, ["a.mp4", "b.pdf"])


def test_doc_content_type_single_pdf() -> None:
    assert _resolve_input_type("doc", False, ["manuale.pdf"]) == "pdf"


def test_doc_content_type_multiple_images_become_image_type() -> None:
    assert _resolve_input_type("doc", False, ["a.png", "b.jpg"]) == "image"


def test_doc_content_type_multiple_non_image_files_rejected() -> None:
    with pytest.raises(ValueError, match="singolo documento"):
        _resolve_input_type("doc", False, ["a.pdf", "b.docx"])


def test_doc_content_type_unsupported_extension_raises() -> None:
    with pytest.raises(Exception):
        _resolve_input_type("doc", False, ["a.zip"])
