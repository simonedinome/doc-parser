from datetime import datetime, timezone

from doc_parser.output.naming import run_label, run_timestamp, slugify, unique_dir


def test_slugify_handles_accents_and_symbols() -> None:
    assert slugify("Formazione: Fatturazione & Note di Credito!") == "formazione-fatturazione-note-di-credito"
    assert slugify("Perché è così") == "perche-e-cosi"
    assert slugify("***") == "run"


def test_label_prefers_cli_name_then_file_then_title() -> None:
    assert run_label("cli-formazione-gestionale", "webinar.mp4", "Titolo") == "formazione-gestionale"
    assert run_label("sessione-ui", "Webinar Giugno.mp4", "Titolo") == "webinar-giugno"
    assert run_label("sessione-ui", "3 file", "Gestione tariffe") == "gestione-tariffe"
    assert run_label("sessione-ui", "run", None) == "run"


def test_timestamp_is_local_and_minute_precise() -> None:
    moment = datetime(2026, 11, 24, 8, 54, 59, tzinfo=timezone.utc)
    assert run_timestamp(moment) == moment.astimezone().strftime("%Y-%m-%d_%H%M")
    assert run_timestamp(datetime(2026, 1, 2, 3, 4)) == "2026-01-02_0304"


def test_unique_dir_adds_counter(tmp_path) -> None:
    assert unique_dir(tmp_path, "serie") == tmp_path / "serie"
    (tmp_path / "serie").mkdir()
    (tmp_path / "serie_2").mkdir()
    assert unique_dir(tmp_path, "serie") == tmp_path / "serie_3"
