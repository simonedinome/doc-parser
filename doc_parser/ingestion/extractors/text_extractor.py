"""Estrazione testo locale da .csv e .txt: normalizzazione encoding."""

from __future__ import annotations

import csv
import io


def extract_txt(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def extract_csv(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    return "\n".join(" | ".join(row) for row in reader)
