import json
from datetime import date, datetime
from pathlib import Path

import pytest

from doc_parser.core.models import RunRecord
from doc_parser.pipeline.inputs import describe_inputs, load_inputs, normalize_recorded_at, save_manifest
from doc_parser.storage.sqlite_repo import SqliteRepository


@pytest.fixture
def repo(tmp_path: Path) -> SqliteRepository:
    return SqliteRepository(data_dir=tmp_path / "data")


def _run(**overrides) -> RunRecord:
    base = dict(session_id="s1", requester_upn="u@x", input_filename="3 file", input_type="video", content_type="video")
    base.update(overrides)
    return RunRecord(**base)


def test_describe_inputs_assigns_ids_in_upload_order() -> None:
    descriptors = describe_inputs(
        [("webinar.mp4", "webinar", "2026-06-03"), ("slide.pdf", None, None), ("pillola.mp4", "pillola", date(2026, 9, 12))]
    )
    assert descriptors == [
        {"filename": "webinar.mp4", "input_id": "v1", "role": "video", "kind": "webinar", "recorded_at": "2026-06-03"},
        {"filename": "slide.pdf", "input_id": "pdf", "role": "slides"},
        {"filename": "pillola.mp4", "input_id": "v2", "role": "video", "kind": "pillola", "recorded_at": "2026-09-12"},
    ]


def test_describe_inputs_defaults_kind_to_webinar() -> None:
    assert describe_inputs([("a.mp4", None, None)])[0]["kind"] == "webinar"


def test_describe_inputs_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="Tipo di video non valido"):
        describe_inputs([("a.mp4", "seminario", None)])


@pytest.mark.parametrize("value", ["03/06/2026", "2026-6-3", "2026-02-30", datetime(2026, 6, 3, 10, 0)])
def test_normalize_recorded_at_rejects_invalid_values(value) -> None:
    with pytest.raises(ValueError, match="Data di registrazione non valida"):
        normalize_recorded_at(value)


def test_save_manifest_keeps_homonymous_files_apart(repo: SqliteRepository) -> None:
    run = _run()
    descriptors = describe_inputs([("video.mp4", "webinar", None), ("video.mp4", "pillola", None)])
    run.input_manifest_ref = save_manifest(repo, run.run_id, descriptors, [b"primo", b"secondo"])

    loaded = load_inputs(run, repo)

    assert [f.data for f in loaded] == [b"primo", b"secondo"]
    assert [f.filename for f in loaded] == ["video.mp4", "video.mp4"]
    assert [(f.input_id, f.kind) for f in loaded] == [("v1", "webinar"), ("v2", "pillola")]


def test_load_inputs_old_manifest_gets_defaults(repo: SqliteRepository) -> None:
    run = _run()
    ref_a = repo.save_input_file(run.run_id, "a.mp4", b"a")
    ref_pdf = repo.save_input_file(run.run_id, "deck.pdf", b"%PDF-")
    ref_b = repo.save_input_file(run.run_id, "b.mp4", b"b")
    manifest = [
        {"filename": "a.mp4", "path_ref": ref_a},
        {"filename": "deck.pdf", "path_ref": ref_pdf},
        {"filename": "b.mp4", "path_ref": ref_b},
    ]
    run.input_manifest_ref = repo.save_input_file(run.run_id, "manifest.json", json.dumps(manifest).encode())

    loaded = load_inputs(run, repo)

    assert [(f.input_id, f.role, f.kind, f.recorded_at) for f in loaded] == [
        ("v1", "video", "webinar", None),
        ("pdf", "slides", None, None),
        ("v2", "video", "webinar", None),
    ]


def test_load_inputs_single_file_run(repo: SqliteRepository) -> None:
    run = _run(input_filename="solo.mp4")
    run.input_path = repo.save_input_file(run.run_id, "solo.mp4", b"x")
    loaded = load_inputs(run, repo)
    assert len(loaded) == 1 and loaded[0].input_id == "v1" and loaded[0].kind == "webinar"
