"""Estrazione testo locale da .doc legacy (binario OLE) via LibreOffice headless.

Richiede il binario di sistema `soffice` (LibreOffice), analogamente a ffmpeg
per i video: nessun binario .doc viene mai inviato ai modelli.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from doc_parser.core.errors import GuardrailRejection


def extract_doc(data: bytes, timeout: int = 60) -> str:
    with tempfile.TemporaryDirectory(prefix="doc_parser_doc_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_path = tmp_path / "input.doc"
        input_path.write_bytes(data)
        cmd = [
            "soffice",
            "--headless",
            "--convert-to", "txt:Text",
            "--outdir", str(tmp_path),
            str(input_path),
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True, timeout=timeout)
        except FileNotFoundError as exc:
            raise GuardrailRejection(
                "LibreOffice (soffice) non è installato: impossibile convertire i file .doc"
            ) from exc
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise GuardrailRejection(f"Conversione del file .doc fallita: {exc}") from exc

        output_path = tmp_path / "input.txt"
        if not output_path.exists():
            raise GuardrailRejection("Conversione del file .doc non ha prodotto testo")
        return output_path.read_text(encoding="utf-8", errors="replace")
