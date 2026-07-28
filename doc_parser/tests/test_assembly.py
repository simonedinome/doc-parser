import zipfile
from io import BytesIO
from pathlib import Path

from doc_parser.output.assembly import build_artifacts, build_output_zip
from doc_parser.output.logger import Logger


def _data() -> dict:
    return {
        "title": "Titolo",
        "summary": "Sommario",
        "prerequisites": [],
        "procedures": [{"id": "proc_001", "title": "P1", "steps": [{"number": 1, "title": "S1", "description": "D", "notes": ""}]}],
        "glossary": [],
        "notes": [],
    }


def test_build_artifacts_only_selected_artifacts_are_produced() -> None:
    log = Logger()
    log.log("INFO", "run avviata")
    files = build_artifacts(_data(), "video.mp4", "it", ["html_standalone", "procedura"], {}, log)
    assert set(files) == {"procedura.txt", "documentazione_standalone.html", "log.txt"}


def test_build_artifacts_both_html_variants_when_both_selected() -> None:
    files = build_artifacts(_data(), "video.mp4", "it", ["html_standalone", "html_folder"], {}, Logger())
    assert "documentazione.html" in files
    assert "documentazione_standalone.html" in files


def test_build_artifacts_empty_selection_only_has_log() -> None:
    files = build_artifacts(_data(), "video.mp4", "it", [], {}, Logger())
    assert set(files) == {"log.txt"}


def test_build_output_zip_contains_all_artifacts(tmp_path: Path) -> None:
    output_artifacts = ["html_standalone", "html_folder", "procedura", "glossario", "rag_chunks"]
    files, zip_bytes = build_output_zip(_data(), "video.mp4", "it", output_artifacts, {}, tmp_path, Logger())
    names = zipfile.ZipFile(BytesIO(zip_bytes)).namelist()
    for name in files:
        assert name in names
