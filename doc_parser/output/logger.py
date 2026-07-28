"""Logger in-memory della generazione e builder del file di log testuale."""

from __future__ import annotations

import datetime

from doc_parser.output.strings import get_strings


class Logger:
    """Logger in-memory che accumula le righe per il file di log finale."""

    def __init__(self) -> None:
        self._lines: list[str] = []

    def log(self, level: str, message: str) -> None:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._lines.append(f"[{ts}] [{level}] {message}")

    @property
    def lines(self) -> list[str]:
        return list(self._lines)


def build_log_txt(log_lines: list[str], language: str = "it") -> str:
    """Costruisce il file di log testuale dalle righe raccolte."""
    s = get_strings(language)
    header = ["=" * 60, s["log_header"], "=" * 60, ""]
    return "\n".join(header + log_lines + [""])
