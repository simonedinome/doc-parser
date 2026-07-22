import pytest

from doc_parser.pipeline.language import apply_language_directive


def test_apply_language_directive_italian_appends_without_rewriting() -> None:
    original = "Prompt originale."
    result = apply_language_directive(original, "it")
    assert result.startswith(original)
    assert "italiano" in result


def test_apply_language_directive_english_appends() -> None:
    result = apply_language_directive("Prompt originale.", "en")
    assert "English" in result


def test_apply_language_directive_unsupported_language_raises() -> None:
    with pytest.raises(ValueError, match="non supportata"):
        apply_language_directive("Prompt", "fr")
