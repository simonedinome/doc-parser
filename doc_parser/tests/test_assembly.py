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


def test_build_artifacts_standalone_mode_produces_expected_files() -> None:
    log = Logger()
    log.log("INFO", "run avviata")
    files = build_artifacts(_data(), "video.mp4", "it", "standalone", {}, log)
    assert set(files) == {"procedura.txt", "glossario.txt", "rag_chunks.jsonl", "documentazione_standalone.html", "log.txt"}


def test_build_artifacts_both_mode_includes_both_html() -> None:
    files = build_artifacts(_data(), "video.mp4", "it", "both", {}, Logger())
    assert "documentazione.html" in files
    assert "documentazione_standalone.html" in files


def test_build_output_zip_contains_all_artifacts(tmp_path: Path) -> None:
    files, zip_bytes = build_output_zip(_data(), "video.mp4", "it", "both", {}, tmp_path, Logger())
    names = zipfile.ZipFile(BytesIO(zip_bytes)).namelist()
    for name in files:
        assert name in names
