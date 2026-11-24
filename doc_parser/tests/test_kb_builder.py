"""TXT Knowledge base: sezioni autosufficienti entro il budget, senza provenienza."""

from doc_parser.output.kb_builder import KB_SECTION_MAX_CHARS, SECTION_SEPARATOR, build_kb_txt

LONG_ANSWER = " ".join(f"Frase numero {i} della risposta completa con dettagli operativi." for i in range(60))


def _data() -> dict:
    return {
        "title": "Fatturazione elettronica",
        "summary": "Come emettere e correggere le fatture.",
        "prerequisites": ["Accesso al gestionale"],
        "concepts": [{"id": "con_001", "title": "Nota di credito", "content": "Documento che storna una fattura.",
                      "sources": [{"filename": "webinar.mp4", "timestamps": ["00:10"]}], "merged_from": ["v1/con_001"]}],
        "procedures": [{
            "id": "proc_001", "title": "Emettere una fattura",
            "steps": [{"number": n, "title": f"Passaggio {n}", "description": f"Descrizione dettagliata del passaggio {n}. " * 6,
                       "notes": "Attenzione ai dati IVA." if n == 2 else "", "source_timestamps": ["01:00"],
                       "sources": [{"filename": "webinar.mp4"}]} for n in range(1, 13)],
        }],
        "qa": [
            {"id": "qa_001", "question": "Si può annullare una fattura inviata?", "answer": "No, si emette una nota di credito."},
            {"id": "qa_002", "question": "Quanto tempo serve per lo scarto SDI?", "answer": LONG_ANSWER},
        ],
        "glossary": [{"term": "SDI", "definition": "Sistema di Interscambio"}],
        "notes": ["Le fatture si conservano per 10 anni."],
    }


def _sections(text: str) -> list[str]:
    return [section.strip() for section in text.split(SECTION_SEPARATOR)]


def test_every_section_fits_budget_and_repeats_topic() -> None:
    sections = _sections(build_kb_txt(_data()))
    assert all(len(section) <= KB_SECTION_MAX_CHARS for section in sections)
    assert all(section.startswith("### ") and "| Argomento: Fatturazione elettronica" in section.split("\n")[0]
               for section in sections)


def test_order_and_kinds() -> None:
    headers = [section.split("\n")[0] for section in _sections(build_kb_txt(_data()))]
    kinds = [header[4:].split(":")[0].split(" |")[0] for header in headers]
    first = {kind: kinds.index(kind) for kind in dict.fromkeys(kinds)}
    assert list(first) == ["Panoramica", "Concetto", "Procedura", "Domanda e risposta", "Glossario", "Note generali"]


def test_long_procedure_is_split_in_parts_with_title_repeated() -> None:
    headers = [s.split("\n")[0] for s in _sections(build_kb_txt(_data())) if s.startswith("### Procedura")]
    assert len(headers) >= 2
    assert all("Emettere una fattura (parte" in header for header in headers)
    text = build_kb_txt(_data())
    assert all(f"Passo {n} — Passaggio {n}" in text for n in range(1, 13))
    assert "Nota: Attenzione ai dati IVA." in text


def test_qa_is_complete_even_when_split() -> None:
    sections = [s for s in _sections(build_kb_txt(_data())) if "Quanto tempo serve" in s.split("\n")[0]]
    assert len(sections) >= 2
    body = " ".join(" ".join(s.split("\n")[2:]) for s in sections)
    for i in range(60):
        assert f"Frase numero {i} " in body
    assert "Domanda: Si può annullare una fattura inviata?\nRisposta: No, si emette una nota di credito." in build_kb_txt(_data())


def test_no_provenance_in_text() -> None:
    text = build_kb_txt(_data())
    assert "webinar.mp4" not in text and "00:10" not in text and "v1/con_001" not in text


def test_english_labels() -> None:
    text = build_kb_txt(_data(), language="en")
    assert "### Overview | Topic: Fatturazione elettronica" in text
    assert "Question: Si può annullare" in text and "### Procedure: Emettere una fattura (part 1 of" in text


def test_minimal_json_without_optional_blocks() -> None:
    text = build_kb_txt({"title": "", "summary": "S", "procedures": []})
    assert text.startswith("### Panoramica | Argomento: Senza titolo")
    assert "Glossario" not in text and "Domanda" not in text
