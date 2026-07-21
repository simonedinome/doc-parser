"""Impacchettamento in ZIP (in memoria) degli artefatti di una run."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


def create_zip(files: dict[str, bytes], screenshot_dir: Path | None, output_artifacts: list[str]) -> bytes:
    """Crea uno ZIP in memoria e ne ritorna i byte.

    Parameters
    ----------
    files:
        Mappa ``{nome_file: contenuto}`` per gli artefatti già selezionati
        (il filtro per ``output_artifacts`` è già stato applicato a monte,
        in ``build_artifacts``).
    screenshot_dir:
        Cartella con gli screenshot PNG (può essere None).
    output_artifacts:
        Chiavi degli artefatti selezionati dall'utente. La cartella
        ``screenshots/`` viene inclusa solo se è stato selezionato
        ``"html_folder"`` (l'unico artefatto che vi fa riferimento con
        percorsi relativi; lo standalone incorpora le immagini in base64).
    """
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)

        if "html_folder" in output_artifacts and screenshot_dir is not None and screenshot_dir.exists():
            for img in sorted(screenshot_dir.glob("*.png")):
                zf.write(img, f"screenshots/{img.name}")

    return buf.getvalue()
