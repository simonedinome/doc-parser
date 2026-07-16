from datetime import datetime, timezone

from doc_parser.core.models import RunRecord, RunStatus
from doc_parser.ui.format import download_filename, friendly_row, has_active, origin_label


def _run(**overrides) -> RunRecord:
    base = dict(session_id="s1", requester_upn="u@x", input_filename="doc.pdf")
    base.update(overrides)
    return RunRecord(**base)


def test_origin_label_empty_for_top_level_run() -> None:
    assert origin_label(_run()) == ""


def test_origin_label_shows_parent_short_id() -> None:
    run = _run(parent_run_id="abcdef1234567890")
    assert origin_label(run) == "Rielaborazione di run #abcdef12"


def test_download_filename_documentazione_mode_is_zip() -> None:
    run = _run(input_filename="manuale.pdf", output_mode="documentazione")
    assert download_filename(run) == "manuale.zip"


def test_download_filename_kb_densa_mode_is_txt() -> None:
    run = _run(input_filename="manuale.pdf", output_mode="kb_densa")
    assert download_filename(run) == "manuale.txt"


def test_download_filename_falls_back_to_run_id_without_filename() -> None:
    run = _run(input_filename="")
    assert download_filename(run) == f"{run.run_id[:8]}.zip"


def test_friendly_row_includes_model_costs_and_origin() -> None:
    run = _run(
        model_id="anthropic/claude-haiku-4.5",
        step1_cost_eur=0.001234,
        step2_cost_eur=0.005678,
        parent_run_id="parent123456",
        status=RunStatus.DONE,
        completed_at=datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc),
    )
    row = friendly_row(run)
    assert row["Modello"] == "anthropic/claude-haiku-4.5"
    assert row["Costo step1 (EUR)"] == "0.0012"
    assert row["Costo step2 (EUR)"] == "0.0057"
    assert row["Origine"] == "Rielaborazione di run #parent12"
    assert row["Stato"] == "✅ Completata"


def test_friendly_row_blank_costs_when_not_set() -> None:
    row = friendly_row(_run())
    assert row["Costo step1 (EUR)"] == ""
    assert row["Costo step2 (EUR)"] == ""
    assert row["Modello"] == ""


def test_has_active_true_when_queued_or_processing() -> None:
    assert has_active([_run(status=RunStatus.QUEUED)]) is True
    assert has_active([_run(status=RunStatus.PROCESSING)]) is True
    assert has_active([_run(status=RunStatus.DONE)]) is False
