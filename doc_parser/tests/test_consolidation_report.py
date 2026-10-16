from doc_parser.output.consolidation_report import build_consolidation_lines
from doc_parser.output.logger import Logger, build_log_txt


def _ref(ref, filename, kind, recorded_at, timestamps=(), slide=None, title=""):
    return {"ref": ref, "input_id": ref.split("/")[0], "filename": filename, "kind": kind, "recorded_at": recorded_at,
            "timestamps": list(timestamps), "slide": slide, "step_title": title}


def _data(chosen=None, discarded=None) -> dict:
    chosen = chosen or _ref("v1/proc_001/1", "webinar.mp4", "webinar", "2026-06-03", ["00:10"], title="Apri Tariffe")
    discarded = discarded or [
        _ref("v2/proc_001/1", "pillola.mp4", "pillola", "2026-09-12", ["00:05"]),
        _ref("pdf/2", "deck.pdf", "slide", None, slide=2),
    ]
    return {
        "procedures": [],
        "source_inputs": [
            {"input_id": "v1", "filename": "webinar.mp4", "role": "video", "kind": "webinar", "recorded_at": "2026-06-03"},
            {"input_id": "v2", "filename": "pillola.mp4", "role": "video", "kind": "pillola", "recorded_at": "2026-09-12"},
            {"input_id": "pdf", "filename": "deck.pdf", "role": "slides", "pages": 4},
        ],
        "consolidation_log": {
            "priority_order": ["v1", "pdf", "v2"],
            "conflicts": [{"topic": "Nome del menu", "reason": "Il webinar mostra il menu", "chosen": chosen, "discarded": discarded}],
            "dropped": [{**_ref("v1/proc_002/1", "webinar.mp4", "webinar", "2026-06-03", ["59:00"], title="Saluti"), "reason": "saluti"}],
            "skipped_slides": [{"slide": 1, "reason": "copertina"}],
            "uncovered_slides": [3],
            "warnings": ["Consolidamento riuscito al tentativo 2 di 3"],
        },
    }


def test_report_renders_sources_conflicts_dropped_slides_and_warnings() -> None:
    text = "\n".join(build_consolidation_lines(_data(), "it"))
    assert "== FONTI ==" in text
    assert "- v2 · pillola · registrato il 2026-09-12 · pillola.mp4" in text
    assert "- pdf · slide · deck.pdf · 4 pagine" in text
    assert "Ordine di priorità: v1 > pdf > v2" in text
    assert "== DISCORDANZE ==" in text
    assert "- Tema: Nome del menu" in text
    assert "Fonte tenuta: webinar.mp4 (webinar, registrato il 2026-06-03) · 00:10 · «Apri Tariffe»" in text
    assert "Fonte scartata: deck.pdf (slide) · slide 2" in text
    assert "Motivo: Il webinar mostra il menu" in text
    assert "webinar.mp4 (webinar, registrato il 2026-06-03) · 59:00 · «Saluti»: saluti" in text
    assert "- Slide 1: copertina" in text and "- Slide 3: non inclusa e non motivata" in text
    assert "- Consolidamento riuscito al tentativo 2 di 3" in text


def test_report_flags_more_recent_discarded_source() -> None:
    lines = build_consolidation_lines(_data(), "it")
    flagged = [line for line in lines if "ATTENZIONE" in line]
    assert len(flagged) == 1
    assert flagged[0].strip().startswith("ATTENZIONE: fonte scartata più recente, verificare")
    assert "pillola.mp4" in flagged[0]


def test_report_no_recency_flag_when_discarded_is_older_or_undated() -> None:
    chosen = _ref("v2/proc_001/1", "pillola.mp4", "pillola", "2026-09-12")
    discarded = [_ref("v1/proc_001/1", "webinar.mp4", "webinar", "2026-06-03"), _ref("v3/proc_001/1", "x.mp4", "webinar", None)]
    assert not any("ATTENZIONE" in line for line in build_consolidation_lines(_data(chosen, discarded), "it"))


def test_report_english_labels() -> None:
    text = "\n".join(build_consolidation_lines(_data(), "en"))
    assert "== SOURCES ==" in text and "== DISCREPANCIES ==" in text and "== WARNINGS ==" in text
    assert "short video, recorded on 2026-09-12" in text
    assert "WARNING: discarded source is more recent, please check" in text
    assert "Slide 3: not included, no reason given" in text


def test_report_empty_for_runs_without_consolidation() -> None:
    assert build_consolidation_lines({"title": "T", "procedures": []}, "it") == []
    log = Logger()
    log.log("INFO", "Run completata")
    log.add_block(build_consolidation_lines({"procedures": []}, "it"))
    assert len(log.lines) == 1


def test_report_lines_are_added_without_timestamp_prefix() -> None:
    log = Logger()
    log.add_block(build_consolidation_lines(_data(), "it"))
    txt = build_log_txt(log.lines, "it")
    assert "\n== FONTI ==\n" in txt
