import pytest

from doc_parser.pipeline.step2_validate import Step2ValidationError, validate_step2_output


def _raw() -> dict:
    return {
        "procedures": [
            {
                "id": "proc_001",
                "title": "Originale",
                "steps": [
                    {"number": 1, "timestamp": "00:10", "title": "S1", "description": "d1"},
                    {"number": 2, "timestamp": "00:20", "title": "S2", "description": "d2"},
                ],
            }
        ]
    }


def test_valid_rewrite_only_changes_prose() -> None:
    rewritten = {
        "procedures": [
            {
                "id": "proc_001",
                "title": "Titolo migliorato",
                "steps": [
                    {"number": 1, "timestamp": "00:10", "title": "Step migliorato", "description": "meglio"},
                    {"number": 2, "timestamp": "00:20", "title": "S2", "description": "d2 meglio"},
                ],
            }
        ]
    }
    validate_step2_output(_raw(), rewritten)  # non deve sollevare


def test_altered_step_timestamp_raises() -> None:
    rewritten = _raw()
    rewritten["procedures"][0]["steps"][0]["timestamp"] = "00:11"
    with pytest.raises(Step2ValidationError, match="ID/timestamp alterati"):
        validate_step2_output(_raw(), rewritten)


def test_altered_step_number_raises() -> None:
    rewritten = _raw()
    rewritten["procedures"][0]["steps"][0]["number"] = 5
    with pytest.raises(Step2ValidationError):
        validate_step2_output(_raw(), rewritten)


def test_altered_procedure_id_raises() -> None:
    rewritten = _raw()
    rewritten["procedures"][0]["id"] = "proc_999"
    with pytest.raises(Step2ValidationError, match="ID di 'procedures' alterati"):
        validate_step2_output(_raw(), rewritten)


def test_procedure_count_mismatch_raises() -> None:
    rewritten = {"procedures": []}
    with pytest.raises(Step2ValidationError, match="Cardinalità"):
        validate_step2_output(_raw(), rewritten)


def test_step_count_mismatch_raises() -> None:
    rewritten = _raw()
    rewritten["procedures"][0]["steps"].pop()
    with pytest.raises(Step2ValidationError, match="Cardinalità di step"):
        validate_step2_output(_raw(), rewritten)


def test_source_timestamps_must_match_for_video() -> None:
    raw = {"procedures": [{"id": "proc_001", "steps": [{"number": 1, "source_timestamps": ["01:00", "02:00"]}]}]}
    rewritten = {"procedures": [{"id": "proc_001", "steps": [{"number": 1, "source_timestamps": ["01:00"]}]}]}
    with pytest.raises(Step2ValidationError):
        validate_step2_output(raw, rewritten)


def test_concepts_validated_like_procedures() -> None:
    raw = {"concepts": [{"id": "con_001"}], "procedures": []}
    rewritten = {"concepts": [{"id": "con_999"}], "procedures": []}
    with pytest.raises(Step2ValidationError, match="ID di 'concepts' alterati"):
        validate_step2_output(raw, rewritten)
