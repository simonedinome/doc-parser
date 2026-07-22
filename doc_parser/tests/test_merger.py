from doc_parser.pipeline.merger import merge_run_results


def test_merge_single_video_passthrough_semantics() -> None:
    data = {
        "title": "Video A",
        "summary": "Riassunto A",
        "prerequisites": ["Req1"],
        "procedures": [{"id": "proc_001", "title": "P1", "steps": []}],
        "glossary": [{"term": "X", "definition": "Y"}],
        "notes": ["Nota1"],
    }
    merged = merge_run_results([(data, "a.mp4")], "run")
    assert merged["title"] == "Video A"
    assert merged["procedures"][0]["id"] == "proc_001"


def test_merge_title_falls_back_to_run_name() -> None:
    data = {"title": "", "summary": "", "prerequisites": [], "procedures": [], "glossary": [], "notes": []}
    merged = merge_run_results([(data, "a.mp4")], "run_fallback")
    assert merged["title"] == "run_fallback"


def test_merge_reassigns_sequential_procedure_ids_without_dedup() -> None:
    data_a = {"title": "A", "summary": "", "prerequisites": [], "procedures": [{"id": "proc_001", "title": "Uno", "steps": []}], "glossary": [], "notes": []}
    data_b = {"title": "B", "summary": "", "prerequisites": [], "procedures": [{"id": "proc_001", "title": "Due", "steps": []}, {"id": "proc_002", "title": "Tre", "steps": []}], "glossary": [], "notes": []}
    merged = merge_run_results([(data_a, "a.mp4"), (data_b, "b.mp4")], "run")
    ids = [p["id"] for p in merged["procedures"]]
    assert ids == ["proc_001", "proc_002", "proc_003"]
    assert len(merged["procedures"]) == 3


def test_merge_dedups_glossary_prerequisites_notes_case_insensitive() -> None:
    data_a = {"title": "A", "summary": "", "prerequisites": ["Requisito X"], "procedures": [], "glossary": [{"term": "API", "definition": "d1"}], "notes": ["nota comune"]}
    data_b = {"title": "B", "summary": "", "prerequisites": ["requisito x"], "procedures": [], "glossary": [{"term": "api", "definition": "d2"}], "notes": ["nota comune"]}
    merged = merge_run_results([(data_a, "a.mp4"), (data_b, "b.mp4")], "run")
    assert merged["prerequisites"] == ["Requisito X"]
    assert len(merged["glossary"]) == 1 and merged["glossary"][0]["definition"] == "d1"
    assert merged["notes"] == ["nota comune"]


def test_merge_concepts_deduped_by_title_and_reindexed() -> None:
    data_a = {"title": "A", "summary": "", "prerequisites": [], "procedures": [], "glossary": [], "notes": [], "concepts": [{"id": "con_001", "title": "Concetto X", "content": "c1"}]}
    data_b = {"title": "B", "summary": "", "prerequisites": [], "procedures": [], "glossary": [], "notes": [], "concepts": [{"id": "con_001", "title": "concetto x", "content": "c2"}, {"id": "con_002", "title": "Concetto Y", "content": "c3"}]}
    merged = merge_run_results([(data_a, "a.mp4"), (data_b, "b.mp4")], "run")
    assert [c["id"] for c in merged["concepts"]] == ["con_001", "con_002"]
    assert merged["concepts"][0]["content"] == "c1"


def test_merge_omits_concepts_key_when_absent() -> None:
    data = {"title": "A", "summary": "", "prerequisites": [], "procedures": [], "glossary": [], "notes": []}
    merged = merge_run_results([(data, "a.mp4")], "run")
    assert "concepts" not in merged


def test_merge_summary_joins_all_non_empty() -> None:
    data_a = {"title": "A", "summary": "Parte 1", "prerequisites": [], "procedures": [], "glossary": [], "notes": []}
    data_b = {"title": "B", "summary": "Parte 2", "prerequisites": [], "procedures": [], "glossary": [], "notes": []}
    merged = merge_run_results([(data_a, "a.mp4"), (data_b, "b.mp4")], "run")
    assert "Parte 1" in merged["summary"] and "Parte 2" in merged["summary"]
