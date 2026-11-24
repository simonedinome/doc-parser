"""Consolidamento delle serie nelle run con artefatto kb: concetti e Q&A sorgente."""

import copy

import pytest

from doc_parser.pipeline.consolidation import build_index, build_request, enrich, normalize_step1, validate
from doc_parser.pipeline.consolidation_prompts import CONSOLIDATION_KB_SYSTEM_ADDENDUM, CONSOLIDATION_KB_USER_ADDENDUM
from doc_parser.pipeline.kb_addendum import KB_MARKER, mark_kb_extraction
from doc_parser.tests.test_consolidation import PILLOLA, SLIDES, WEBINAR, _step1_pillola, _step1_webinar, _valid_output


def _with_kb(step1: dict, concepts: list[dict], qa: list[dict]) -> dict:
    data = copy.deepcopy(step1)
    data["concepts"] = concepts
    data["qa"] = qa
    return mark_kb_extraction(normalize_step1(data))


@pytest.fixture
def kb_index():
    webinar = _with_kb(
        _step1_webinar(),
        [{"id": "con_009", "title": "Tariffa", "content": "Una tariffa è un listino.", "embedding_keywords": ["tariffa"]}],
        [{"question": "Posso cancellare una tariffa?", "answer": "Sì, se non è usata da contratti attivi."}],
    )
    pillola = _with_kb(
        _step1_pillola(),
        [],
        [{"question": "Si può eliminare una tariffa?", "answer": "Solo se nessun contratto la usa."}],
    )
    return build_index([(WEBINAR, webinar), (PILLOLA, pillola)], SLIDES, slide_count=4)


def _kb_output() -> dict:
    output = _valid_output()
    output["concepts"].append({"merged_from": ["v1/con_001"], "slides": []})
    output["qa"] = [
        {"question": "Si può eliminare una tariffa?", "answer": "Sì, solo se nessun contratto attivo la usa.",
         "merged_from": ["v1/qa_001", "v2/qa_001"]},
    ]
    return output


def test_normalize_step1_renumbers_concepts_and_qa(kb_index) -> None:
    assert set(kb_index.kb_items) == {"v1/con_001", "v1/qa_001", "v2/qa_001"}
    assert kb_index.kb is True


def test_request_lists_kb_refs_and_appends_addendum(kb_index) -> None:
    system, user, _ = build_request(kb_index, "it")
    assert CONSOLIDATION_KB_SYSTEM_ADDENDUM in system
    assert system.endswith("Scrivi l'intera documentazione in italiano.")
    assert CONSOLIDATION_KB_USER_ADDENDUM in user
    assert '"ref": "v1/con_001"' in user and '"ref": "v2/qa_001"' in user
    assert KB_MARKER not in user


def test_request_without_kb_is_unchanged() -> None:
    index = build_index([(WEBINAR, _step1_webinar()), (PILLOLA, _step1_pillola())], SLIDES, slide_count=4)
    system, user, _ = build_request(index, "it")
    assert index.kb is False and not index.kb_items
    assert CONSOLIDATION_KB_SYSTEM_ADDENDUM not in system
    assert CONSOLIDATION_KB_USER_ADDENDUM not in user


def test_valid_kb_output_has_no_blocking_issues(kb_index) -> None:
    validation = validate(_kb_output(), kb_index)
    assert validation.blocking == []
    concept = validation.output["concepts"][-1]
    assert concept["title"] == "Tariffa" and concept["content"] == "Una tariffa è un listino."  # forma breve


def test_uncovered_qa_is_blocking(kb_index) -> None:
    output = _kb_output()
    output["qa"][0]["merged_from"] = ["v1/qa_001"]
    validation = validate(output, kb_index)
    assert any("v2/qa_001" in issue for issue in validation.blocking)


def test_qa_can_be_dropped_with_reason(kb_index) -> None:
    output = _kb_output()
    output["qa"][0]["merged_from"] = ["v1/qa_001"]
    output["dropped"].append({"ref": "v2/qa_001", "reason": "duplicato"})
    validation = validate(output, kb_index)
    assert validation.blocking == []
    enriched = enrich(validation, kb_index)
    dropped = [d for d in enriched["consolidation_log"]["dropped"] if d["ref"] == "v2/qa_001"]
    assert dropped[0]["step_title"] == "Si può eliminare una tariffa?"


def test_qa_without_answer_is_blocking(kb_index) -> None:
    output = _kb_output()
    output["qa"].append({"question": "Domanda", "answer": "", "merged_from": ["v1/qa_001", "v2/qa_001"]})
    assert any("question o answer" in issue for issue in validate(output, kb_index).blocking)


def test_enrich_carries_qa_and_marker(kb_index) -> None:
    enriched = enrich(validate(_kb_output(), kb_index), kb_index)
    assert enriched[KB_MARKER] is True
    assert enriched["qa"][0]["id"] == "qa_001"
    assert enriched["qa"][0]["answer"] == "Sì, solo se nessun contratto attivo la usa."
    assert [s["input_id"] for s in enriched["qa"][0]["sources"]] == ["v1", "v2"]


def test_enrich_without_kb_has_no_qa() -> None:
    index = build_index([(WEBINAR, _step1_webinar()), (PILLOLA, _step1_pillola())], SLIDES, slide_count=4)
    enriched = enrich(validate(_valid_output(), index), index)
    assert "qa" not in enriched and KB_MARKER not in enriched
