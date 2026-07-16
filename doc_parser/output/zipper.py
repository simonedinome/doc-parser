"""Impacchettamento in ZIP (in memoria) degli artefatti di una run."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


def create_zip(files: dict[str, bytes], screenshot_dir: Path | None, mode: str) -> bytes:
    """Crea uno ZIP in memoria e ne ritorna i byte.

    Parameters
    ----------
    files:
        Mappa ``{nome_file: contenuto}`` per gli artefatti testuali/HTML.
    screenshot_dir:
        Cartella con gli screenshot PNG (può essere None).
    mode:
        ``"standalone"``, ``"folder"`` o ``"both"``.
    """
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            if mode == "standalone" and name == "documentazione.html":
                continue
            if mode == "folder" and name == "documentazione_standalone.html":
                continue
            zf.writestr(name, content)

        if mode in ("folder", "both") and screenshot_dir is not None and screenshot_dir.exists():
            for img in sorted(screenshot_dir.glob("*.png")):
                zf.write(img, f"screenshots/{img.name}")

    return buf.getvalue()
