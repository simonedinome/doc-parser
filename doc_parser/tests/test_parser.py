import json

import pytest

from doc_parser.pipeline.parser import normalize_to_procedures, parse_response


def _screencast_json(**overrides) -> str:
    data = {
        "title": "Titolo",
        "summary": "Sommario",
        "prerequisites": [],
        "steps": [{"number": 1, "timestamp": "00:10", "title": "S1", "description": "D1", "notes": "", "embedding_keywords": []}],
        "glossary": [],
        "notes": [],
    }
    data.update(overrides)
    return json.dumps(data)


def test_parse_screencast_normalizes_to_procedures() -> None:
    data = parse_response(_screencast_json(), "screencast")
    assert data["procedures"][0]["id"] == "proc_001"
    assert data["procedures"][0]["steps"][0]["number"] == 1


def test_parse_strips_markdown_code_fence() -> None:
    raw = "```json\n" + _screencast_json() + "\n```"
    data = parse_response(raw, "screencast")
    assert data["title"] == "Titolo"


def test_parse_malformed_json_raises_value_error() -> None:
    with pytest.raises(ValueError, match="JSON non valido"):
        parse_response("{questo non è json", "screencast")


def test_parse_truncated_json_raises_value_error() -> None:
    truncated = _screencast_json()[:-5]
    with pytest.raises(ValueError):
        parse_response(truncated, "screencast")


def test_parse_screencast_missing_keys_raises() -> None:
    raw = json.dumps({"title": "T"})
    with pytest.raises(ValueError, match="Chiavi obbligatorie mancanti"):
        parse_response(raw, "screencast")


def test_parse_screencast_empty_steps_raises() -> None:
    raw = _screencast_json(steps=[])
    with pytest.raises(ValueError, match="almeno uno step"):
        parse_response(raw, "screencast")


def test_parse_webinar_with_procedures() -> None:
    raw = json.dumps(
        {
            "title": "T", "summary": "S", "prerequisites": [],
            "procedures": [{"id": "proc_001", "title": "P1", "steps": [{"number": 1, "title": "S1", "description": "D", "notes": "", "source_timestamps": ["01:00"], "embedding_keywords": []}]}],
            "glossary": [], "notes": [],
        }
    )
    data = parse_response(raw, "webinar")
    assert data["procedures"][0]["id"] == "proc_001"


def test_parse_webinar_normalizes_flat_steps() -> None:
    data = parse_response(_screencast_json(), "webinar")
    assert data["procedures"][0]["id"] == "proc_001"


def test_parse_webinar_empty_procedures_raises() -> None:
    raw = json.dumps({"title": "T", "summary": "S", "prerequisites": [], "procedures": [], "glossary": [], "notes": []})
    with pytest.raises(ValueError, match="almeno una procedura"):
        parse_response(raw, "webinar")


def test_parse_webinar_procedure_without_steps_raises() -> None:
    raw = json.dumps(
        {
            "title": "T", "summary": "S", "prerequisites": [],
            "procedures": [{"id": "proc_001", "title": "P1", "steps": []}],
            "glossary": [], "notes": [],
        }
    )
    with pytest.raises(ValueError, match="almeno uno step"):
        parse_response(raw, "webinar")


def test_parse_hybrid_keeps_concepts_and_procedures() -> None:
    raw = json.dumps(
        {
            "title": "T", "summary": "S", "prerequisites": [],
            "concepts": [{"id": "con_001", "title": "C1", "content": "...", "embedding_keywords": []}],
            "procedures": [{"id": "proc_001", "title": "P1", "steps": [{"number": 1, "title": "S1", "description": "D", "notes": "", "source_timestamps": [], "embedding_keywords": []}]}],
            "glossary": [], "notes": [],
        }
    )
    data = parse_response(raw, "hybrid")
    assert len(data["concepts"]) == 1
    assert len(data["procedures"]) == 1


def test_parse_hybrid_requires_at_least_one_concept_or_procedure() -> None:
    raw = json.dumps({"title": "T", "summary": "S", "prerequisites": [], "concepts": [], "procedures": [], "glossary": [], "notes": []})
    with pytest.raises(ValueError, match="almeno un concetto"):
        parse_response(raw, "hybrid")


def test_parse_doc_profile_uses_flat_steps_branch() -> None:
    data = parse_response(_screencast_json(), "doc")
    assert data["procedures"][0]["steps"][0]["number"] == 1


def test_normalize_to_procedures_is_idempotent() -> None:
    already = {"procedures": [{"id": "proc_001", "title": "T", "steps": []}]}
    assert normalize_to_procedures(already) == already
