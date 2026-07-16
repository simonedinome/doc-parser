"""Dispatcher degli estrattori locali in base al tipo di contenuto rilevato."""

from __future__ import annotations

from doc_parser.ingestion.extractors.docx_extractor import extract_docx
from doc_parser.ingestion.extractors.text_extractor import extract_csv, extract_txt
from doc_parser.ingestion.extractors.xlsx_extractor import extract_xlsx

LOCAL_EXTRACTION_KINDS = {"docx", "xlsx", "csv", "txt"}


def extract_text(content_kind: str, data: bytes, max_rows_per_sheet: int = 5000) -> str:
    if content_kind == "docx":
        return extract_docx(data)
    if content_kind == "xlsx":
        return extract_xlsx(data, max_rows_per_sheet)
    if content_kind == "csv":
        return extract_csv(data)
    if content_kind == "txt":
        return extract_txt(data)
    raise ValueError(f"Tipo di contenuto non estraibile localmente: {content_kind!r}")
