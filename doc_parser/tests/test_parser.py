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


def test_parse_video_with_procedures() -> None:
    raw = json.dumps(
        {
            "title": "T", "summary": "S", "prerequisites": [],
            "procedures": [{"id": "proc_001", "title": "P1", "steps": [{"number": 1, "title": "S1", "description": "D", "notes": "", "source_timestamps": ["01:00"], "embedding_keywords": []}]}],
            "glossary": [], "notes": [],
        }
    )
    data = parse_response(raw, "video")
    assert data["procedures"][0]["id"] == "proc_001"


def test_parse_video_normalizes_flat_steps() -> None:
    data = parse_response(_screencast_json(), "video")
    assert data["procedures"][0]["id"] == "proc_001"


def test_parse_video_empty_procedures_raises() -> None:
    raw = json.dumps({"title": "T", "summary": "S", "prerequisites": [], "procedures": [], "glossary": [], "notes": []})
    with pytest.raises(ValueError, match="almeno una procedura"):
        parse_response(raw, "video")


def test_parse_video_procedure_without_steps_raises() -> None:
    raw = json.dumps(
        {
            "title": "T", "summary": "S", "prerequisites": [],
            "procedures": [{"id": "proc_001", "title": "P1", "steps": []}],
            "glossary": [], "notes": [],
        }
    )
    with pytest.raises(ValueError, match="almeno uno step"):
        parse_response(raw, "video")


def test_parse_manuale_keeps_concepts_and_procedures() -> None:
    raw = json.dumps(
        {
            "title": "T", "summary": "S", "prerequisites": [],
            "concepts": [{"id": "con_001", "title": "C1", "content": "...", "embedding_keywords": []}],
            "procedures": [{"id": "proc_001", "title": "P1", "steps": [{"number": 1, "title": "S1", "description": "D", "notes": "", "source_pages": [], "embedding_keywords": []}]}],
            "glossary": [], "notes": [],
        }
    )
    data = parse_response(raw, "manuale")
    assert len(data["concepts"]) == 1
    assert len(data["procedures"]) == 1


def test_parse_manuale_requires_at_least_one_concept_or_procedure() -> None:
    raw = json.dumps({"title": "T", "summary": "S", "prerequisites": [], "concepts": [], "procedures": [], "glossary": [], "notes": []})
    with pytest.raises(ValueError, match="almeno un concetto"):
        parse_response(raw, "manuale")


def test_parse_manuale_normalizes_source_pages_to_list() -> None:
    raw = json.dumps(
        {
            "title": "T", "summary": "S", "prerequisites": [],
            "concepts": [],
            "procedures": [{"id": "proc_001", "title": "P1", "steps": [{"number": 1, "title": "S1", "description": "D", "notes": "", "source_pages": "Pagina 3", "embedding_keywords": []}]}],
            "glossary": [], "notes": [],
        }
    )
    data = parse_response(raw, "manuale")
    assert data["procedures"][0]["steps"][0]["source_pages"] == []


def test_parse_doc_profile_uses_flat_steps_branch() -> None:
    data = parse_response(_screencast_json(), "documento")
    assert data["procedures"][0]["steps"][0]["number"] == 1


def test_normalize_to_procedures_is_idempotent() -> None:
    already = {"procedures": [{"id": "proc_001", "title": "T", "steps": []}]}
    assert normalize_to_procedures(already) == already


def test_parse_video_normalizes_source_slides_to_int_list() -> None:
    import json

    from doc_parser.pipeline.parser import parse_response

    raw = json.dumps(
        {
            "title": "T", "summary": "S", "prerequisites": [], "glossary": [], "notes": [],
            "procedures": [
                {
                    "id": "proc_001", "title": "P1",
                    "steps": [
                        {"number": 1, "title": "S1", "description": "D", "source_slides": [3, "Slide 5", "5", 0, None, 2.0, True]},
                        {"number": 2, "title": "S2", "description": "D", "source_slides": "slide 7"},
                        {"number": 3, "title": "S3", "description": "D"},
                    ],
                }
            ],
        }
    )
    steps = parse_response(raw, "video")["procedures"][0]["steps"]
    assert steps[0]["source_slides"] == [3, 5, 2]
    assert steps[1]["source_slides"] == [7]
    assert "source_slides" not in steps[2]
