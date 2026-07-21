from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from doc_parser.core.models import RunRecord, RunStatus
from doc_parser.storage.sqlite_repo import SqliteRepository
from doc_parser.ui.format import (
    cost_summary_windows,
    download_filename,
    friendly_row,
    has_active,
    origin_label,
)


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
    assert row["Costo (EUR)"] == ""
    assert row["Costo step1 (EUR)"] == ""
    assert row["Costo step2 (EUR)"] == ""
    assert row["Modello"] == ""


def test_friendly_row_includes_total_cost_for_single_step_runs() -> None:
    # Le run non-video (documenti/immagini) valorizzano solo cost_eur, mai
    # step1/step2_cost_eur: la colonna "Costo (EUR)" deve comunque comparire.
    run = _run(cost_eur=0.012345, status=RunStatus.DONE)
    row = friendly_row(run)
    assert row["Costo (EUR)"] == "0.0123"
    assert row["Costo step1 (EUR)"] == ""
    assert row["Costo step2 (EUR)"] == ""


def test_has_active_true_when_queued_or_processing() -> None:
    assert has_active([_run(status=RunStatus.QUEUED)]) is True
    assert has_active([_run(status=RunStatus.PROCESSING)]) is True
    assert has_active([_run(status=RunStatus.DONE)]) is False


@pytest.fixture
def repo(tmp_path: Path) -> SqliteRepository:
    return SqliteRepository(data_dir=tmp_path / "data")


def test_cost_summary_windows_filters_by_upn(repo: SqliteRepository) -> None:
    now = datetime.now(timezone.utc)
    repo.create_run(_run(requester_upn="a@x", session_id="sa", created_at=now, cost_eur=1.0))
    repo.create_run(_run(requester_upn="b@x", session_id="sb", created_at=now, cost_eur=2.0))

    all_rows = cost_summary_windows(repo)
    label_24h, rows_24h = all_rows[0]
    assert label_24h == "Ultime 24 ore"
    assert {r["group_key"] for r in rows_24h} == {"a@x", "b@x"}

    filtered = cost_summary_windows(repo, upn="a@x")
    _, rows_a = filtered[0]
    assert len(rows_a) == 1
    assert rows_a[0]["group_key"] == "a@x"
    assert rows_a[0]["cost_eur"] == pytest.approx(1.0)


def test_cost_summary_windows_excludes_runs_outside_all_windows(repo: SqliteRepository) -> None:
    now = datetime.now(timezone.utc)
    repo.create_run(_run(requester_upn="old@x", session_id="s-old", created_at=now - timedelta(days=40), cost_eur=9.0))

    for _, rows in cost_summary_windows(repo):
        assert rows == []
