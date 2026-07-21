import zipfile
from io import BytesIO
from pathlib import Path

from doc_parser.output.zipper import create_zip


def _files() -> dict[str, bytes]:
    return {
        "procedura.txt": b"testo",
        "documentazione.html": b"<html>folder</html>",
        "documentazione_standalone.html": b"<html>standalone</html>",
    }


def test_zip_includes_all_files_passed_in() -> None:
    zip_bytes = create_zip(_files(), None, ["html_standalone"])
    names = zipfile.ZipFile(BytesIO(zip_bytes)).namelist()
    assert set(names) == set(_files())


def test_zip_includes_screenshots_when_html_folder_selected(tmp_path: Path) -> None:
    (tmp_path / "proc_001_step_001.png").write_bytes(b"PNG")
    zip_bytes = create_zip(_files(), tmp_path, ["html_folder"])
    names = zipfile.ZipFile(BytesIO(zip_bytes)).namelist()
    assert "screenshots/proc_001_step_001.png" in names


def test_zip_excludes_screenshots_without_html_folder(tmp_path: Path) -> None:
    (tmp_path / "proc_001_step_001.png").write_bytes(b"PNG")
    zip_bytes = create_zip(_files(), tmp_path, ["html_standalone"])
    names = zipfile.ZipFile(BytesIO(zip_bytes)).namelist()
    assert not any(n.startswith("screenshots/") for n in names)


def test_zip_missing_screenshot_dir_does_not_crash() -> None:
    zip_bytes = create_zip(_files(), None, ["html_standalone", "html_folder"])
    assert len(zip_bytes) > 0
