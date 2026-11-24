"""Percorsi completi con artefatto kb: serie consolidata, step 2, Rielabora e --resume."""

import json

import pytest

from doc_parser.core.models import RunRecord, RunStatus
from doc_parser.pipeline.core import process_run
from doc_parser.pipeline.kb_addendum import KB_MARKER, KB_SYSTEM_ADDENDUM
from doc_parser.tests.test_pipeline_consolidated import (  # noqa: F401 (fixture)
    OPENROUTER_MODEL,
    PILLOLA_STEP1,
    SONNET_MODEL,
    STEP1_MODEL,
    WEBINAR_STEP1,
    FnProvider,
    _failed_mother,
    _resume,
    consolidated_run,
    consolidation_response,
    no_ffmpeg,
    patch_providers,
    repo,
    settings,
    step2_echo,
)

_QA_WEBINAR = {"question": "Si può eliminare una tariffa?", "answer": "Sì, solo se nessun contratto attivo la usa."}
_QA_PILLOLA = {"question": "Posso cancellare una tariffa?", "answer": "Solo senza contratti collegati."}


def _with_kb_fields(response, concepts, qa):
    raw, t_in, t_out = response
    data = json.loads(raw)
    data["concepts"] = concepts
    data["qa"] = qa
    return json.dumps(data), t_in, t_out


WEBINAR_KB = _with_kb_fields(
    WEBINAR_STEP1, [{"id": "con_001", "title": "Tariffe", "content": "Una tariffa è un listino prezzi."}], [_QA_WEBINAR]
)
PILLOLA_KB = _with_kb_fields(PILLOLA_STEP1, [], [_QA_PILLOLA])


def kb_consolidation_response():
    raw, t_in, t_out = consolidation_response()
    data = json.loads(raw)
    data["concepts"].append({"merged_from": ["v1/con_001"], "slides": []})
    data["qa"] = [{"question": _QA_WEBINAR["question"], "answer": _QA_WEBINAR["answer"], "merged_from": ["v1/qa_001", "v2/qa_001"]}]
    return json.dumps(data), t_in, t_out


def step2_that_damages_qa(system_prompt, user_prompt):
    """Step 2 che, se vedesse le Q&A, le riassumerebbe: non deve vederle."""
    assert '"qa"' not in user_prompt and KB_MARKER not in user_prompt
    return step2_echo()(system_prompt, user_prompt)


def _run_kb_series(monkeypatch, repo, settings, output_artifacts="procedura,kb"):
    run = consolidated_run(repo, OPENROUTER_MODEL, output_artifacts=output_artifacts)
    step1 = FnProvider([WEBINAR_KB, PILLOLA_KB])
    model = FnProvider([kb_consolidation_response(), step2_that_damages_qa])
    patch_providers(monkeypatch, {STEP1_MODEL: step1, OPENROUTER_MODEL: model})
    process_run(run, repo, settings)
    return repo.get_run(run.run_id), step1, model


def test_kb_series_keeps_concepts_and_full_qa_through_step2(monkeypatch, repo, settings) -> None:
    run, step1, model = _run_kb_series(monkeypatch, repo, settings)

    assert run.status == RunStatus.DONE, run.error_message
    assert all(KB_SYSTEM_ADDENDUM in call[0] for call in step1.calls)
    assert '"ref": "v2/qa_001"' in model.calls[0][1]
    final = json.loads(repo.get_file(run.final_json_ref))
    assert final[KB_MARKER] is True
    assert [q["answer"] for q in final["qa"]] == [_QA_WEBINAR["answer"]]
    assert final["qa"][0]["sources"][0]["filename"] == "webinar.mp4"
    assert any(con["content"] == "Una tariffa è un listino prezzi." for con in final["concepts"])
    assert final["title"] == "Manuale rifinito"  # lo step 2 ha comunque riscritto il resto
    step1_saved = json.loads(repo.get_output_file(run.run_id, "step1_v1.json"))
    assert step1_saved[KB_MARKER] is True


def test_series_without_kb_sends_no_kb_addendum(monkeypatch, repo, settings) -> None:
    run = consolidated_run(repo, OPENROUTER_MODEL)
    step1 = FnProvider([WEBINAR_STEP1, PILLOLA_STEP1])
    model = FnProvider([consolidation_response(), step2_echo()])
    patch_providers(monkeypatch, {STEP1_MODEL: step1, OPENROUTER_MODEL: model})

    process_run(run, repo, settings)

    assert repo.get_run(run.run_id).status == RunStatus.DONE
    assert all(KB_SYSTEM_ADDENDUM not in call[0] for call in step1.calls)
    assert "qa_" not in model.calls[0][1]
    final = json.loads(repo.get_file(repo.get_run(run.run_id).final_json_ref))
    assert "qa" not in final and KB_MARKER not in final


def _rework(repo, parent, output_artifacts):
    child = RunRecord(
        session_id="s1", requester_upn="utente@demo.local", input_filename=parent.input_filename, input_type="video",
        content_type="video", model_id=OPENROUTER_MODEL, output_artifacts=output_artifacts, parent_run_id=parent.run_id,
    )
    return repo.create_run(child)


def test_rework_with_kb_of_run_without_kb_is_rejected(monkeypatch, repo, settings) -> None:
    parent = consolidated_run(repo, OPENROUTER_MODEL)
    patch_providers(monkeypatch, {
        STEP1_MODEL: FnProvider([WEBINAR_STEP1, PILLOLA_STEP1]),
        OPENROUTER_MODEL: FnProvider([consolidation_response(), step2_echo()]),
    })
    process_run(parent, repo, settings)
    child = _rework(repo, repo.get_run(parent.run_id), "kb")

    with pytest.raises(Exception, match="rifai la run completa"):
        process_run(child, repo, settings)


def test_rework_with_kb_of_kb_run_keeps_qa(monkeypatch, repo, settings) -> None:
    parent, _, _ = _run_kb_series(monkeypatch, repo, settings)
    child = _rework(repo, parent, "kb")
    patch_providers(monkeypatch, {OPENROUTER_MODEL: FnProvider([step2_that_damages_qa])})

    process_run(child, repo, settings)

    final = json.loads(repo.get_file(repo.get_run(child.run_id).final_json_ref))
    assert final["qa"][0]["answer"] == _QA_WEBINAR["answer"]


def test_resume_with_kb_redoes_step1_extracted_without_kb(monkeypatch, repo, settings) -> None:
    mother = _failed_mother(monkeypatch, repo, settings)  # step 1 senza KB
    child = _resume(repo, mother, output_artifacts="procedura,kb")
    step1 = FnProvider([WEBINAR_KB, PILLOLA_KB])
    patch_providers(monkeypatch, {STEP1_MODEL: step1, SONNET_MODEL: FnProvider([kb_consolidation_response(), step2_echo()])})

    process_run(child, repo, settings)

    updated = repo.get_run(child.run_id)
    assert updated.status == RunStatus.DONE, updated.error_message
    assert len(step1.calls) == 2
    final = json.loads(repo.get_file(updated.final_json_ref))
    assert final["qa"][0]["question"] == _QA_WEBINAR["question"]
