import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from doc_parser.pipeline.screenshots import (
    _timestamp_to_seconds,
    extract_pdf_pages,
    extract_screenshots,
    video_duration_seconds,
)


def _ffprobe_result(duration: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["ffprobe"], 0, stdout=duration, stderr="")


def test_timestamp_to_seconds_mm_ss() -> None:
    assert _timestamp_to_seconds("01:30") == 90.0


def test_timestamp_to_seconds_hh_mm_ss() -> None:
    assert _timestamp_to_seconds("01:02:03") == 3723.0


def test_timestamp_to_seconds_invalid_format_raises() -> None:
    with pytest.raises(ValueError):
        _timestamp_to_seconds("non-un-timestamp")


def test_video_duration_seconds_parses_output(tmp_path: Path) -> None:
    with patch("doc_parser.pipeline.screenshots.subprocess.run", return_value=_ffprobe_result("125.4\n")):
        assert video_duration_seconds(tmp_path / "v.mp4") == 125.4


def test_video_duration_seconds_returns_none_on_failure(tmp_path: Path) -> None:
    with patch("doc_parser.pipeline.screenshots.subprocess.run", side_effect=FileNotFoundError()):
        assert video_duration_seconds(tmp_path / "v.mp4") is None


def _dispatch_side_effect(duration_str: str):
    def _run(cmd, **kwargs):
        if cmd[0] == "ffprobe":
            return _ffprobe_result(duration_str)
        out_path = Path(cmd[-1])
        out_path.write_bytes(b"PNG")
        return subprocess.CompletedProcess(cmd, 0)

    return _run


def test_extract_screenshots_writes_files_for_each_step(tmp_path: Path) -> None:
    procedures = [{"id": "proc_001", "steps": [{"number": 1, "timestamp": "00:05"}]}]
    with patch(
        "doc_parser.pipeline.screenshots.subprocess.run", side_effect=_dispatch_side_effect("60.0")
    ):
        result = extract_screenshots(tmp_path / "v.mp4", procedures, tmp_path / "out")
    key = ("proc_001", 1)
    assert result[key] is not None
    assert result[key].exists()


def test_extract_screenshots_missing_timestamp_returns_none(tmp_path: Path) -> None:
    procedures = [{"id": "proc_001", "steps": [{"number": 1, "timestamp": ""}]}]
    with patch(
        "doc_parser.pipeline.screenshots.subprocess.run", side_effect=_dispatch_side_effect("60.0")
    ):
        result = extract_screenshots(tmp_path / "v.mp4", procedures, tmp_path / "out")
    assert result[("proc_001", 1)] is None


def test_extract_screenshots_clamps_timestamp_beyond_duration_and_warns(tmp_path: Path) -> None:
    procedures = [{"id": "proc_001", "steps": [{"number": 1, "timestamp": "00:30"}]}]
    warnings: list[str] = []
    calls: list[list[str]] = []

    def _run(cmd, **kwargs):
        if cmd[0] == "ffprobe":
            return _ffprobe_result("10.0")
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"PNG")
        return subprocess.CompletedProcess(cmd, 0)

    with patch("doc_parser.pipeline.screenshots.subprocess.run", side_effect=_run):
        extract_screenshots(tmp_path / "v.mp4", procedures, tmp_path / "out", warn=warnings.append)

    assert len(warnings) == 1
    assert "oltre la durata" in warnings[0]
    ss_index = calls[0].index("-ss")
    seconds_used = float(calls[0][ss_index + 1])
    assert seconds_used < 10.0


def test_extract_screenshots_ffmpeg_failure_returns_none(tmp_path: Path) -> None:
    procedures = [{"id": "proc_001", "steps": [{"number": 1, "timestamp": "00:05"}]}]

    def _run(cmd, **kwargs):
        if cmd[0] == "ffprobe":
            raise FileNotFoundError()
        raise subprocess.CalledProcessError(1, cmd)

    with patch("doc_parser.pipeline.screenshots.subprocess.run", side_effect=_run):
        result = extract_screenshots(tmp_path / "v.mp4", procedures, tmp_path / "out")
    assert result[("proc_001", 1)] is None


def _sample_pdf_bytes(pages: int = 2) -> bytes:
    import fitz

    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Pagina {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def test_extract_pdf_pages_renders_referenced_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(_sample_pdf_bytes(pages=3))
    procedures = [{"id": "proc_001", "steps": [{"number": 1, "timestamp": "Pagina 2"}]}]
    result = extract_pdf_pages(pdf_path, procedures, tmp_path / "out")
    key = ("proc_001", 1)
    assert result[key] is not None and result[key].exists()


def test_extract_pdf_pages_out_of_range_returns_none(tmp_path: Path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(_sample_pdf_bytes(pages=1))
    procedures = [{"id": "proc_001", "steps": [{"number": 1, "timestamp": "Pagina 99"}]}]
    result = extract_pdf_pages(pdf_path, procedures, tmp_path / "out")
    assert result[("proc_001", 1)] is None
