import json

from doc_parser.output.rag_builder import build_rag_jsonl


def _data() -> dict:
    return {
        "title": "Titolo",
        "summary": "Sommario",
        "prerequisites": ["Req 1"],
        "procedures": [
            {
                "id": "proc_001",
                "title": "Procedura A",
                "steps": [
                    {"number": 1, "title": "Step 1", "description": "Usa la API per fare X", "notes": "", "embedding_keywords": ["api", "x"]}
                ],
            }
        ],
        "glossary": [{"term": "API", "definition": "Interfaccia"}],
        "concepts": [{"id": "con_001", "title": "Concetto X", "content": "Spiega X", "embedding_keywords": ["x"]}],
    }


def _load_chunks(jsonl: str) -> list[dict]:
    return [json.loads(line) for line in jsonl.splitlines()]


def test_rag_jsonl_has_summary_concept_step_glossary_chunks() -> None:
    chunks = _load_chunks(build_rag_jsonl(_data(), "video.mp4"))
    types = [c["chunk_type"] for c in chunks]
    assert types == ["summary", "concept", "step", "glossary"]


def test_rag_summary_chunk_includes_prerequisites() -> None:
    chunks = _load_chunks(build_rag_jsonl(_data(), "video.mp4"))
    summary_chunk = chunks[0]
    assert summary_chunk["chunk_id"] == "video_summary"
    assert "Req 1" in summary_chunk["content"]


def test_rag_step_chunk_detects_glossary_terms() -> None:
    chunks = _load_chunks(build_rag_jsonl(_data(), "video.mp4"))
    step_chunk = next(c for c in chunks if c["chunk_type"] == "step")
    assert step_chunk["glossary_terms"] == ["API"]
    assert step_chunk["chunk_id"] == "video_proc_proc_001_step_001"


def test_rag_glossary_chunk_lists_all_terms() -> None:
    chunks = _load_chunks(build_rag_jsonl(_data(), "video.mp4"))
    glossary_chunk = chunks[-1]
    assert "API: Interfaccia" in glossary_chunk["content"]


def test_rag_jsonl_is_valid_ndjson_one_object_per_line() -> None:
    raw = build_rag_jsonl(_data(), "video.mp4")
    for line in raw.splitlines():
        json.loads(line)  # non deve sollevare
