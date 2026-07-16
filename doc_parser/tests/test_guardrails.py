import pytest

from doc_parser.core.errors import GuardrailRejection
from doc_parser.ingestion.guardrails import (
    check_size,
    classify_extension,
    inspect_pdf,
    sha256_hash,
)


def _sample_pdf(pages: int = 2) -> bytes:
    import fitz

    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Pagina {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def _encrypted_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "segreto")
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    doc.close()
    return data


ZERO_PAGE_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj
trailer << /Root 1 0 R >>
%%EOF"""


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("video.mp4", "video"),
        ("clip.MOV", "video"),
        ("foto.png", "image"),
        ("doc.pdf", "pdf"),
        ("cartella.xlsx", "xlsx"),
        ("relazione.docx", "docx"),
        ("dati.csv", "csv"),
        ("note.txt", "txt"),
    ],
)
def test_classify_extension(filename: str, expected: str) -> None:
    assert classify_extension(filename) == expected


def test_classify_extension_unsupported_raises() -> None:
    with pytest.raises(GuardrailRejection, match="non supportata"):
        classify_extension("archivio.zip")


def test_check_size_within_limit_ok() -> None:
    check_size(1024, max_mb=1)


def test_check_size_over_limit_raises() -> None:
    with pytest.raises(GuardrailRejection, match="MB"):
        check_size(2 * 1024 * 1024, max_mb=1)


def test_inspect_pdf_valid() -> None:
    assert inspect_pdf(_sample_pdf(pages=3), max_pages=10) == 3


def test_inspect_pdf_non_pdf_raises() -> None:
    with pytest.raises(GuardrailRejection, match="non è un PDF"):
        inspect_pdf(b"non sono un pdf", max_pages=10)


def test_inspect_pdf_encrypted_raises() -> None:
    with pytest.raises(GuardrailRejection, match="cifrato"):
        inspect_pdf(_encrypted_pdf(), max_pages=10)


def test_inspect_pdf_zero_pages_raises() -> None:
    with pytest.raises(GuardrailRejection, match="0 pagine"):
        inspect_pdf(ZERO_PAGE_PDF, max_pages=10)


def test_inspect_pdf_too_many_pages_raises() -> None:
    with pytest.raises(GuardrailRejection, match="pagine"):
        inspect_pdf(_sample_pdf(pages=11), max_pages=10)


def test_sha256_hash_is_deterministic() -> None:
    assert sha256_hash(b"stesso contenuto") == sha256_hash(b"stesso contenuto")
    assert sha256_hash(b"a") != sha256_hash(b"b")
