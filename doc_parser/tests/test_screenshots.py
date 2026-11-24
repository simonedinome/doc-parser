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


# --- extract_step_images (percorso consolidato) ---


def _consolidated(sources, slides=(), concept_slides=()):
    return {
        "procedures": [{"id": "proc_001", "steps": [{"number": 1, "sources": list(sources), "source_slides": list(slides)}]}],
        "concepts": [{"id": "con_001", "source_slides": list(concept_slides)}],
    }


_WEBINAR_SRC = {"input_id": "v1", "filename": "web.mp4", "kind": "webinar", "recorded_at": "2026-06-03", "timestamps": ["00:10"]}
_PILLOLA_SRC = {"input_id": "v2", "filename": "pil.mp4", "kind": "pillola", "recorded_at": "2026-09-12", "timestamps": ["00:05"]}


def _ffmpeg_recorder(fail_inputs=()):
    used: list[str] = []

    def _run(cmd, **kwargs):
        if cmd[0] == "ffprobe":
            return _ffprobe_result("120.0")
        video = cmd[cmd.index("-i") + 1]
        used.append(Path(video).name)
        if Path(video).name in fail_inputs:
            raise subprocess.CalledProcessError(1, cmd)
        Path(cmd[-1]).write_bytes(b"PNG")
        return subprocess.CompletedProcess(cmd, 0)

    return _run, used


def _setup(tmp_path: Path):
    from doc_parser.pipeline.screenshots import extract_step_images

    pdf = tmp_path / "deck.pdf"
    pdf.write_bytes(_sample_pdf_bytes(pages=3))
    videos = {"v1": tmp_path / "web.mp4", "v2": tmp_path / "pil.mp4"}
    return extract_step_images, pdf, videos, tmp_path / "out"


def test_step_images_webinar_wins_over_pillola(tmp_path: Path) -> None:
    extract, pdf, videos, out = _setup(tmp_path)
    run, used = _ffmpeg_recorder()
    with patch("doc_parser.pipeline.screenshots.subprocess.run", side_effect=run):
        origins = extract(_consolidated([_WEBINAR_SRC, _PILLOLA_SRC]), videos, pdf, out)
    assert origins[("proc_001", 1)] == "video"
    assert used == ["web.mp4"]


def test_step_images_slide_used_when_no_webinar(tmp_path: Path) -> None:
    extract, pdf, videos, out = _setup(tmp_path)
    run, used = _ffmpeg_recorder()
    with patch("doc_parser.pipeline.screenshots.subprocess.run", side_effect=run):
        origins = extract(_consolidated([_PILLOLA_SRC], slides=[2]), videos, pdf, out)
    assert origins[("proc_001", 1)] == "slide"
    assert used == []
    assert (out / "proc_001_step_001.png").exists()
    assert not (out / "proc_001_step_001_slide.png").exists()  # la principale è già la slide


def test_step_images_pillola_used_last(tmp_path: Path) -> None:
    extract, pdf, videos, out = _setup(tmp_path)
    run, used = _ffmpeg_recorder()
    with patch("doc_parser.pipeline.screenshots.subprocess.run", side_effect=run):
        origins = extract(_consolidated([_PILLOLA_SRC]), videos, pdf, out)
    assert origins[("proc_001", 1)] == "video"
    assert used == ["pil.mp4"]


def test_step_images_failed_extraction_falls_back_to_next_candidate(tmp_path: Path) -> None:
    extract, pdf, videos, out = _setup(tmp_path)
    run, used = _ffmpeg_recorder(fail_inputs={"web.mp4"})
    with patch("doc_parser.pipeline.screenshots.subprocess.run", side_effect=run):
        origins = extract(_consolidated([_WEBINAR_SRC, _PILLOLA_SRC], slides=[3]), videos, pdf, out)
    assert used == ["web.mp4"]
    assert origins[("proc_001", 1)] == "slide"


def test_step_images_secondary_slide_and_concept_slide(tmp_path: Path) -> None:
    extract, pdf, videos, out = _setup(tmp_path)
    run, _ = _ffmpeg_recorder()
    with patch("doc_parser.pipeline.screenshots.subprocess.run", side_effect=run):
        extract(_consolidated([_WEBINAR_SRC], slides=[2], concept_slides=[1]), videos, pdf, out)
    assert (out / "proc_001_step_001.png").read_bytes() == b"PNG"
    assert (out / "proc_001_step_001_slide.png").exists()
    assert (out / "con_001_slide.png").exists()


def test_step_images_all_candidates_failing_leave_no_file(tmp_path: Path) -> None:
    extract, _, videos, out = _setup(tmp_path)
    run, _ = _ffmpeg_recorder(fail_inputs={"web.mp4"})
    with patch("doc_parser.pipeline.screenshots.subprocess.run", side_effect=run):
        origins = extract(_consolidated([_WEBINAR_SRC]), videos, None, out)
    assert origins[("proc_001", 1)] is None
    assert not (out / "proc_001_step_001.png").exists()


def test_step_images_clamp_warning_names_the_file(tmp_path: Path) -> None:
    extract, pdf, videos, out = _setup(tmp_path)
    late = {**_WEBINAR_SRC, "timestamps": ["05:00"]}
    warnings: list[str] = []
    run, _ = _ffmpeg_recorder()
    with patch("doc_parser.pipeline.screenshots.subprocess.run", side_effect=run):
        extract(_consolidated([late]), videos, pdf, out, warn=warnings.append)
    assert len(warnings) == 1 and "web.mp4" in warnings[0] and "oltre la durata" in warnings[0]
