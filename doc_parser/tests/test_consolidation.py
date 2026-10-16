import copy
import json

import pytest

from doc_parser.pipeline.consolidation import (
    ConsolidationValidationError,
    build_index,
    build_request,
    consolidate,
    enrich,
    normalize_step1,
    priority_order,
    validate,
)
from doc_parser.pipeline.inputs import InputFile
from doc_parser.providers.base import BaseProvider

WEBINAR = InputFile("webinar_giugno.mp4", b"w", "v1", "video", "webinar", "2026-06-03")
PILLOLA = InputFile("pillola_settembre.mp4", b"p", "v2", "video", "pillola", "2026-09-12")
SLIDES = InputFile("deck.pdf", b"%PDF-", "pdf", "slides")


def _step(number, title, ts, slides=(), notes=""):
    return {
        "number": number, "title": title, "description": f"Descrizione {title}", "notes": notes,
        "source_timestamps": list(ts), "embedding_keywords": [title.lower()], "source_slides": list(slides),
    }


def _step1_webinar() -> dict:
    return normalize_step1(
        {
            "title": "Webinar", "summary": "S", "prerequisites": ["Accesso"], "glossary": [], "notes": [],
            "procedures": [
                {"id": "proc_001", "title": "Creare una tariffa", "steps": [_step(1, "Apri Tariffe", ["00:10", "05:00"], [2]), _step(2, "Salva", ["01:00"])]},
                {"id": "proc_002", "title": "Saluti", "steps": [_step(1, "Saluti finali", ["59:00"])]},
            ],
        }
    )


def _step1_pillola() -> dict:
    return normalize_step1(
        {
            "title": "Pillola", "summary": "S", "prerequisites": [], "glossary": [], "notes": [],
            "procedures": [{"id": "proc_001", "title": "Tariffa", "steps": [_step(1, "Apri Tariffe", ["00:05"], [2]), _step(2, "Verifica", ["00:30"])]}],
        }
    )


@pytest.fixture
def index():
    return build_index([(WEBINAR, _step1_webinar()), (PILLOLA, _step1_pillola())], SLIDES, slide_count=4)


def _valid_output() -> dict:
    return {
        "title": "Manuale tariffe", "summary": "Come gestire le tariffe.", "prerequisites": ["Accesso"],
        "concepts": [{"title": "Cos'è una tariffa", "content": "Una tariffa è…", "embedding_keywords": ["tariffa"], "merged_from": [], "slides": [3, 4]}],
        "procedures": [
            {
                "title": "Creare una tariffa",
                "steps": [
                    {"title": "Aprire Tariffe", "description": "Navigare in Impostazioni > Tariffe.", "notes": "", "embedding_keywords": ["tariffe"],
                     "merged_from": ["v1/proc_001/1", "v2/proc_001/1"], "slides": [2]},
                    {"merged_from": ["v1/proc_001/2"]},
                    {"merged_from": ["v2/proc_001/2"]},
                ],
            }
        ],
        "glossary": [{"term": "Tariffa", "definition": "Prezzo"}],
        "notes": ["Domanda: … / Risposta: …"],
        "conflicts": [{"topic": "Nome del menu", "chosen": "v1/proc_001/1", "discarded": ["v2/proc_001/1", "pdf/2"], "reason": "Il webinar mostra l'interfaccia completa"}],
        "dropped": [{"ref": "v1/proc_002/1", "reason": "saluti"}],
        "skipped_slides": [{"slide": 1, "reason": "copertina"}],
    }


class ScriptedProvider(BaseProvider):
    name = "scripted"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate(self, system_prompt, user_prompt, attachments=None):
        self.calls.append((system_prompt, user_prompt, attachments or []))
        return self._responses.pop(0)


def test_valid_output_has_no_issues(index) -> None:
    result = validate(_valid_output(), index)
    assert result.blocking == []
    assert result.warnings == []


def test_normalize_step1_renumbers_duplicate_ids() -> None:
    data = normalize_step1(
        {"procedures": [{"id": "proc_001", "steps": [{"number": 4}, {"number": 4}]}, {"id": "proc_001", "steps": [{"number": 1}]}]}
    )
    assert [p["id"] for p in data["procedures"]] == ["proc_001", "proc_002"]
    assert [s["number"] for s in data["procedures"][0]["steps"]] == [1, 2]


def test_priority_order_is_total_with_missing_dates() -> None:
    giugno = InputFile("a.mp4", b"", "v1", "video", "webinar", "2026-06-01")
    senza_data = InputFile("b.mp4", b"", "v2", "video", "webinar", None)
    marzo = InputFile("c.mp4", b"", "v3", "video", "webinar", "2026-03-01")
    pillola = InputFile("d.mp4", b"", "v4", "video", "pillola", "2026-10-01")
    assert priority_order([giugno, senza_data, marzo, pillola], SLIDES) == ["v1", "v3", "v2", "pdf", "v4"]


def test_priority_order_same_date_last_uploaded_wins() -> None:
    a = InputFile("a.mp4", b"", "v1", "video", "pillola", None)
    b = InputFile("b.mp4", b"", "v2", "video", "pillola", None)
    assert priority_order([a, b], None) == ["v2", "v1"]


def test_unknown_reference_is_blocking(index) -> None:
    output = _valid_output()
    output["procedures"][0]["steps"][1]["merged_from"] = ["v1/proc_009/1"]
    result = validate(output, index)
    assert any("riferimento inesistente 'v1/proc_009/1'" in b for b in result.blocking)


def test_pdf_reference_beyond_page_count_is_blocking(index) -> None:
    output = _valid_output()
    output["conflicts"][0]["discarded"] = ["pdf/9"]
    assert any("'pdf/9'" in b for b in validate(output, index).blocking)


def test_uncovered_source_step_is_blocking(index) -> None:
    output = _valid_output()
    output["dropped"] = []
    result = validate(output, index)
    assert any("non coperti" in b and "v1/proc_002/1" in b for b in result.blocking)


def test_untraceable_step_is_blocking(index) -> None:
    output = _valid_output()
    output["procedures"][0]["steps"].append({"title": "Inventato", "description": "…", "merged_from": [], "slides": []})
    assert any("non tracciabile" in b for b in validate(output, index).blocking)


def test_multi_reference_step_without_text_is_blocking(index) -> None:
    output = _valid_output()
    output["procedures"][0]["steps"][0] = {"merged_from": ["v1/proc_001/1", "v2/proc_001/1"], "slides": [2]}
    assert any("mancano title o description" in b for b in validate(output, index).blocking)


def test_concept_without_content_is_blocking(index) -> None:
    output = _valid_output()
    output["concepts"][0]["content"] = ""
    assert any("mancano title o content" in b for b in validate(output, index).blocking)


def test_missing_required_key_mentions_truncation(index) -> None:
    output = _valid_output()
    del output["glossary"]
    result = validate(output, index)
    assert result.output is None
    assert "troncata" in result.blocking[0]


def test_single_reference_step_copies_source_text(index) -> None:
    result = validate(_valid_output(), index)
    enriched = enrich(result, index)
    copied = enriched["procedures"][0]["steps"][1]
    assert copied["title"] == "Salva"
    assert copied["description"] == "Descrizione Salva"
    assert copied["embedding_keywords"] == ["salva"]


def test_marker_left_in_copied_notes_is_warning(index) -> None:
    webinar = _step1_webinar()
    webinar["procedures"][0]["steps"][1]["notes"] = "DISCORDANZA SLIDE: la slide 3 indica un altro valore"
    idx = build_index([(WEBINAR, webinar), (PILLOLA, _step1_pillola())], SLIDES, slide_count=4)
    result = validate(_valid_output(), idx)
    assert result.blocking == []
    assert any("DISCORDANZA SLIDE:" in w for w in result.warnings)


def test_priority_violation_is_warning(index) -> None:
    output = _valid_output()
    output["conflicts"][0]["chosen"] = "v2/proc_001/1"
    output["conflicts"][0]["discarded"] = ["v1/proc_001/1"]
    result = validate(output, index)
    assert result.blocking == []
    assert any("priorità più alta" in w for w in result.warnings)


def test_slides_out_of_range_are_removed(index) -> None:
    output = _valid_output()
    output["procedures"][0]["steps"][0]["slides"] = [2, 9]
    result = validate(output, index)
    assert result.blocking == []
    assert result.output["procedures"][0]["steps"][0]["slides"] == [2]
    assert any("slide 9 fuori intervallo" in w for w in result.warnings)


def test_uncovered_slides_are_reported(index) -> None:
    output = _valid_output()
    output["concepts"][0]["slides"] = [4]
    result = validate(output, index)
    assert result.uncovered_slides == [3]
    assert any("slide non incluse" in w and "3" in w for w in result.warnings)
    assert enrich(result, index)["consolidation_log"]["uncovered_slides"] == [3]


def test_enrich_assigns_deterministic_ids(index) -> None:
    enriched = enrich(validate(_valid_output(), index), index)
    assert [c["id"] for c in enriched["concepts"]] == ["con_001"]
    assert [p["id"] for p in enriched["procedures"]] == ["proc_001"]
    assert [s["number"] for s in enriched["procedures"][0]["steps"]] == [1, 2, 3]


def test_enrich_sources_have_kind_date_and_timestamps(index) -> None:
    enriched = enrich(validate(_valid_output(), index), index)
    merged_step = enriched["procedures"][0]["steps"][0]
    assert merged_step["sources"] == [
        {"input_id": "v1", "filename": "webinar_giugno.mp4", "kind": "webinar", "recorded_at": "2026-06-03", "timestamps": ["00:10", "05:00"]},
        {"input_id": "v2", "filename": "pillola_settembre.mp4", "kind": "pillola", "recorded_at": "2026-09-12", "timestamps": ["00:05"]},
    ]
    assert merged_step["source_slides"] == [2]
    assert merged_step["merged_from"] == ["v1/proc_001/1", "v2/proc_001/1"]
    concept = enriched["concepts"][0]
    assert concept["sources"] == [] and concept["source_slides"] == [3, 4]


def test_enrich_resolves_conflicts_and_inputs(index) -> None:
    enriched = enrich(validate(_valid_output(), index), index)
    log = enriched["consolidation_log"]
    assert log["priority_order"] == ["v1", "pdf", "v2"]
    conflict = log["conflicts"][0]
    assert conflict["chosen"]["filename"] == "webinar_giugno.mp4"
    assert conflict["chosen"]["timestamps"] == ["00:10", "05:00"]
    assert [d["kind"] for d in conflict["discarded"]] == ["pillola", "slide"]
    assert conflict["discarded"][1]["slide"] == 2
    assert log["dropped"][0]["reason"] == "saluti" and log["dropped"][0]["filename"] == "webinar_giugno.mp4"
    assert [i["input_id"] for i in enriched["source_inputs"]] == ["v1", "v2", "pdf"]
    assert enriched["source_inputs"][2]["pages"] == 4


def test_build_request_contains_refs_priority_and_pdf(index) -> None:
    system, user, attachments = build_request(index, "it")
    assert '"ref": "v1/proc_001/2"' in user
    assert "=== FONTE v2 · pillola · registrato il 2026-09-12 · pillola_settembre.mp4 ===" in user
    assert "v1 (webinar, 2026-06-03) > pdf (slide) > v2 (pillola, 2026-09-12)" in user
    assert "4 pagine" in user
    assert [a.mime_type for a in attachments] == ["application/pdf"]
    assert system.endswith("Scrivi l'intera documentazione in italiano.")


def test_consolidate_retries_with_request_previous_answer_and_feedback(index) -> None:
    bad = _valid_output()
    bad["conflicts"][0]["chosen"] = "v2/proc_001/1"
    bad["conflicts"][0]["discarded"] = ["v1/proc_001/1"]
    provider = ScriptedProvider([(json.dumps(bad), 100, 10), (json.dumps(_valid_output()), 120, 12)])

    enriched, tokens_in, tokens_out, attempts = consolidate(provider, index, "it", max_attempts=3)

    assert attempts == 2 and tokens_in == 220 and tokens_out == 22
    retry_prompt = provider.calls[1][1]
    assert '"ref": "v1/proc_001/2"' in retry_prompt  # la richiesta originale viaggia di nuovo
    assert json.dumps(bad) in retry_prompt  # con la risposta precedente
    assert "priorità più alta" in retry_prompt  # e il feedback
    assert [a.mime_type for a in provider.calls[1][2]] == ["application/pdf"]
    assert enriched["consolidation_log"]["warnings"] == ["Consolidamento riuscito al tentativo 2 di 3"]


def test_consolidate_accepts_warning_after_last_attempt(index) -> None:
    bad = _valid_output()
    bad["conflicts"][0]["chosen"] = "v2/proc_001/1"
    bad["conflicts"][0]["discarded"] = ["v1/proc_001/1"]
    provider = ScriptedProvider([(json.dumps(bad), 1, 1)] * 2)

    enriched, _, _, attempts = consolidate(provider, index, "it", max_attempts=2)

    assert attempts == 2
    assert any("priorità più alta" in w for w in enriched["consolidation_log"]["warnings"])


def test_consolidate_keeps_last_non_blocking_candidate(index) -> None:
    warning_only = _valid_output()
    warning_only["procedures"][0]["steps"][0]["slides"] = [2, 9]
    broken = copy.deepcopy(_valid_output())
    broken["dropped"] = []
    provider = ScriptedProvider([(json.dumps(warning_only), 1, 1), (json.dumps(broken), 1, 1)])

    enriched, _, _, attempts = consolidate(provider, index, "it", max_attempts=2)

    assert attempts == 1
    assert any("slide 9" in w for w in enriched["consolidation_log"]["warnings"])


def test_consolidate_fails_with_truncation_hint(index) -> None:
    provider = ScriptedProvider([('{"title": "troncato', 1, 1), ('{"title": ', 1, 1)])

    with pytest.raises(ConsolidationValidationError, match="troncata.*step1_v"):
        consolidate(provider, index, "it", max_attempts=2)

    assert "non era un JSON valido" in provider.calls[1][1]
