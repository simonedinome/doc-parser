from doc_parser.output.txt_builder import build_glossario, build_procedura


def _data() -> dict:
    return {
        "title": "Titolo",
        "summary": "Sommario del documento",
        "prerequisites": ["Req 1", "Req 2"],
        "procedures": [
            {
                "id": "proc_001",
                "title": "Procedura A",
                "steps": [
                    {"number": 1, "title": "Step 1", "description": "Descrizione 1", "notes": "Attenzione"},
                    {"number": 2, "title": "Step 2", "description": "Descrizione 2", "notes": ""},
                ],
            }
        ],
        "glossary": [{"term": "API", "definition": "Interfaccia di programmazione"}],
        "notes": ["Nota generale 1"],
    }


def test_build_glossario_italian() -> None:
    txt = build_glossario(_data(), "it")
    assert "GLOSSARIO" in txt
    assert "API" in txt and "Interfaccia di programmazione" in txt


def test_build_glossario_english() -> None:
    txt = build_glossario(_data(), "en")
    assert "GLOSSARY" in txt


def test_build_glossario_empty() -> None:
    txt = build_glossario({"glossary": []}, "it")
    assert "Nessun termine nel glossario." in txt


def test_build_procedura_contains_all_sections_italian() -> None:
    txt = build_procedura(_data(), "video.mp4", "it")
    assert "SOMMARIO" in txt
    assert "PREREQUISITI" in txt
    assert "1. Req 1" in txt
    assert "PROCEDURA 1 — Procedura A" in txt
    assert "STEP 1 — Step 1" in txt
    assert "Note: Attenzione" in txt
    assert "NOTE GENERALI" in txt
    assert "Fonte: video.mp4" in txt


def test_build_procedura_english_labels() -> None:
    txt = build_procedura(_data(), "video.mp4", "en")
    assert "SUMMARY" in txt
    assert "PREREQUISITES" in txt
    assert "PROCEDURE 1" in txt
    assert "STEP 1" in txt
    assert "Source: video.mp4" in txt


def test_build_procedura_no_prerequisites() -> None:
    data = _data()
    data["prerequisites"] = []
    txt = build_procedura(data, "video.mp4", "it")
    assert "Nessun prerequisito." in txt


def test_build_procedura_includes_concepts_when_present() -> None:
    data = _data()
    data["concepts"] = [{"id": "con_001", "title": "Concetto X", "content": "Spiegazione"}]
    txt = build_procedura(data, "video.mp4", "it")
    assert "CONCETTI" in txt
    assert "CONCETTO 1 — Concetto X" in txt
