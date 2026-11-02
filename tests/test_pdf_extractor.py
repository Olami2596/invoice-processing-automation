from pathlib import Path

import pytest
from pdfplumber.utils.exceptions import PdfminerException
from reportlab.pdfgen import canvas

from src.pdf_extractor import extract_text_from_pdf


def test_extract_text_from_sample_invoice():
    project_root = Path(__file__).resolve().parent.parent
    pdf_path = project_root / "data" / "fictional_invoice.pdf"

    extracted_text = extract_text_from_pdf(pdf_path)

    assert "NovaTech Office Solutions" in extracted_text
    assert "INV-2026-1048" in extracted_text
    assert "564,375.00" in extracted_text


def test_extract_text_from_nonexistent_pdf(tmp_path):
    pdf_path = tmp_path / "nonexistent.pdf"

    with pytest.raises(FileNotFoundError):
        extract_text_from_pdf(pdf_path)


def test_extract_text_from_empty_pdf(tmp_path):
    pdf_path = tmp_path / "empty.pdf"

    pdf = canvas.Canvas(str(pdf_path))
    pdf.showPage()
    pdf.save()

    extracted_text = extract_text_from_pdf(pdf_path)

    assert extracted_text == ""


def test_extract_text_from_corrupted_pdf(tmp_path):
    pdf_path = tmp_path / "corrupted.pdf"
    pdf_path.write_text(
        "This is not a valid PDF file.",
        encoding="utf-8",
    )

    with pytest.raises(PdfminerException):
        extract_text_from_pdf(pdf_path)