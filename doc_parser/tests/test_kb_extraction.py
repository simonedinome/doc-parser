"""Addendum KB allo step 1: presente solo con l'artefatto kb, prompt invariati senza."""

import json

from doc_parser.core.models import RunStatus
from doc_parser.pipeline import parser
from doc_parser.pipeline.core import process_run
from doc_parser.pipeline.kb_addendum import (
    KB_MARKER,
    KB_SYSTEM_ADDENDUM,
    apply_kb_addendum,
    kb_requested,
)
from doc_parser.pipeline.language import apply_language_directive
from doc_parser.pipeline.manuale_prompts import MANUALE_SYSTEM_PROMPT, MANUALE_USER_PROMPT
from doc_parser.pipeline.video_prompts import VIDEO_SYSTEM_PROMPT, VIDEO_USER_PROMPT
from doc_parser.tests.test_pipeline_core import (  # noqa: F401 (fixture)
    GEMINI_LITE_MODEL,
    OPENROUTER_MODEL,
    ScriptedProvider,
    _document_run,
    _patch_providers,
    _sample_pdf_bytes,
    _video_run,
    repo,
    settings,
)

_QA = [{"question": "Si può annullare una fattura inviata?", "answer": "No, si emette una nota di credito."}]
_CONCEPTS = [{"id": "con_001", "title": "Nota di credito", "content": "Documento che storna una fattura.", "embedding_keywords": ["nota"]}]


def _video_response(with_kb_fields: bool) -> str:
    data = {
        "title": "Fatturazione",
        "summary": "Sommario",
        "prerequisites": [],
        "procedures": [
            {
                "id": "proc_001",
                "title": "Emettere una fattura",
                "steps": [{"number": 1, "title": "Apri", "description": "Aprire Fatture.", "notes": "",
                           "source_timestamps": ["00:10"], "embedding_keywords": []}],
            }
        ],
        "glossary": [],
        "notes": [],
    }
    if with_kb_fields:
        data["concepts"] = _CONCEPTS
        data["qa"] = _QA
    return json.dumps(data)


def _manuale_response() -> str:
    return json.dumps({
        "title": "Manuale", "summary": "S", "prerequisites": [], "concepts": _CONCEPTS,
        "procedures": [], "glossary": [], "notes": [], "qa": _QA,
    })


def test_kb_requested_reads_csv() -> None:
    assert kb_requested("procedura,kb")
    assert kb_requested(" kb ")
    assert not kb_requested("procedura,rag_chunks")
    assert not kb_requested(None)


def test_addendum_asks_concepts_and_qa_except_for_manuale() -> None:
    system, user = apply_kb_addendum("S", "U", "video")
    assert system == f"S\n\n{KB_SYSTEM_ADDENDUM}"
    assert '"concepts"' in user and '"qa"' in user

    _, user_manuale = apply_kb_addendum("S", "U", "manuale")
    assert '"qa"' in user_manuale and '"concepts"' not in user_manuale


def test_parser_normalizes_qa_without_adding_missing_keys() -> None:
    raw = json.loads(_video_response(with_kb_fields=False))
    plain = parser.parse_response(json.dumps(raw), "video")
    assert "qa" not in plain and "concepts" not in plain

    raw["qa"] = [*_QA, {"question": "Senza risposta", "answer": ""}, "non un dict"]
    parsed = parser.parse_response(json.dumps(raw), "video")
    assert parsed["qa"] == _QA


def test_video_without_kb_sends_unchanged_prompts(monkeypatch, repo, settings) -> None:
    run = _video_run(repo, GEMINI_LITE_MODEL, content_type="video")
    provider = ScriptedProvider([(_video_response(with_kb_fields=False), 100, 50)])
    _patch_providers(monkeypatch, {GEMINI_LITE_MODEL: provider})

    process_run(run, repo, settings)

    system, user, _ = provider.calls[0]
    assert system == apply_language_directive(VIDEO_SYSTEM_PROMPT, "it")
    assert user == VIDEO_USER_PROMPT
    raw = json.loads(repo.get_file(repo.get_run(run.run_id).raw_json_ref))
    assert KB_MARKER not in raw


def test_video_with_kb_appends_addendum_and_marks_raw_json(monkeypatch, repo, settings) -> None:
    run = _video_run(repo, GEMINI_LITE_MODEL, content_type="video", output_artifacts="procedura,kb")
    provider = ScriptedProvider([(_video_response(with_kb_fields=True), 100, 50)])
    _patch_providers(monkeypatch, {GEMINI_LITE_MODEL: provider})

    process_run(run, repo, settings)

    updated = repo.get_run(run.run_id)
    assert updated.status == RunStatus.DONE
    system, user, _ = provider.calls[0]
    expected_system, expected_user = apply_kb_addendum(VIDEO_SYSTEM_PROMPT, VIDEO_USER_PROMPT, "video")
    assert system == apply_language_directive(expected_system, "it")  # lingua sempre ultima
    assert user == expected_user
    raw = json.loads(repo.get_file(updated.raw_json_ref))
    assert raw[KB_MARKER] is True
    assert raw["qa"] == _QA
    assert raw["concepts"][0]["title"] == "Nota di credito"


def test_manuale_pdf_with_kb_asks_only_qa(monkeypatch, repo, settings) -> None:
    run = _document_run(
        repo, "manuale.pdf", _sample_pdf_bytes(), "pdf", OPENROUTER_MODEL,
        output_artifacts="kb", content_type="manuale",
    )
    provider = ScriptedProvider([(_manuale_response(), 100, 50)])
    _patch_providers(monkeypatch, {OPENROUTER_MODEL: provider})

    process_run(run, repo, settings)

    system, user, _ = provider.calls[0]
    expected_system, expected_user = apply_kb_addendum(MANUALE_SYSTEM_PROMPT, MANUALE_USER_PROMPT, "manuale")
    assert system == apply_language_directive(expected_system, "it")
    assert user == expected_user
    final = json.loads(repo.get_file(repo.get_run(run.run_id).final_json_ref))
    assert final[KB_MARKER] is True and final["qa"] == _QA


def test_manuale_pdf_without_kb_sends_unchanged_prompts(monkeypatch, repo, settings) -> None:
    run = _document_run(repo, "manuale.pdf", _sample_pdf_bytes(), "pdf", OPENROUTER_MODEL, content_type="manuale")
    provider = ScriptedProvider([(_manuale_response(), 100, 50)])
    _patch_providers(monkeypatch, {OPENROUTER_MODEL: provider})

    process_run(run, repo, settings)

    system, user, _ = provider.calls[0]
    assert system == apply_language_directive(MANUALE_SYSTEM_PROMPT, "it")
    assert user == MANUALE_USER_PROMPT
