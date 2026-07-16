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


def test_zip_standalone_mode_excludes_folder_html() -> None:
    zip_bytes = create_zip(_files(), None, "standalone")
    names = zipfile.ZipFile(BytesIO(zip_bytes)).namelist()
    assert "documentazione_standalone.html" in names
    assert "documentazione.html" not in names


def test_zip_folder_mode_excludes_standalone_html() -> None:
    zip_bytes = create_zip(_files(), None, "folder")
    names = zipfile.ZipFile(BytesIO(zip_bytes)).namelist()
    assert "documentazione.html" in names
    assert "documentazione_standalone.html" not in names


def test_zip_both_mode_includes_both_html() -> None:
    zip_bytes = create_zip(_files(), None, "both")
    names = zipfile.ZipFile(BytesIO(zip_bytes)).namelist()
    assert "documentazione.html" in names
    assert "documentazione_standalone.html" in names


def test_zip_includes_screenshots_for_folder_and_both(tmp_path: Path) -> None:
    (tmp_path / "proc_001_step_001.png").write_bytes(b"PNG")
    zip_bytes = create_zip(_files(), tmp_path, "folder")
    names = zipfile.ZipFile(BytesIO(zip_bytes)).namelist()
    assert "screenshots/proc_001_step_001.png" in names


def test_zip_excludes_screenshots_for_standalone(tmp_path: Path) -> None:
    (tmp_path / "proc_001_step_001.png").write_bytes(b"PNG")
    zip_bytes = create_zip(_files(), tmp_path, "standalone")
    names = zipfile.ZipFile(BytesIO(zip_bytes)).namelist()
    assert not any(n.startswith("screenshots/") for n in names)


def test_zip_missing_screenshot_dir_does_not_crash() -> None:
    zip_bytes = create_zip(_files(), None, "both")
    assert len(zip_bytes) > 0
