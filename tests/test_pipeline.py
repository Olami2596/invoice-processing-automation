import pytest
from datetime import date
from decimal import Decimal
from src import pipeline
from src.schemas import Invoice, InvoiceProcessingResult


PDF_PATH = "data/fictional_invoice.pdf"

def make_valid_invoice():
    """Create a valid fictional invoice for testing."""

    return Invoice(
        vendor_name="NovaTech Office Solutions",
        customer_name="BrightPath Creative Studio",
        invoice_number="INV-2026-1048",
        invoice_date="2026-10-27",
        due_date="2026-11-10",
        currency="NGN",
        line_items=[
            {
                "description": "Laptop setup and configuration",
                "quantity": Decimal("2"),
                "unit_price": Decimal("185000.00"),
                "amount": Decimal("370000.00"),
            },
            {
                "description": "Network installation",
                "quantity": Decimal("1"),
                "unit_price": Decimal("95000.00"),
                "amount": Decimal("95000.00"),
            },
            {
                "description": "Cloud backup configuration",
                "quantity": Decimal("1"),
                "unit_price": Decimal("60000.00"),
                "amount": Decimal("60000.00"),
            },
        ],
        subtotal=Decimal("525000.00"),
        tax_amount=Decimal("39375.00"),
        total_amount=Decimal("564375.00"),
    )


def test_successfully_processed_invoice(monkeypatch):
    """Test that a valid invoice passes through the pipeline."""

    invoice = make_valid_invoice()

    # Replace the AI extractor with a predictable test function.
    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda invoice_text: invoice,
    )

    result = pipeline.process_invoice(PDF_PATH)

    assert isinstance(result, InvoiceProcessingResult)
    assert result.success is True
    assert result.errors == []
    assert result.source_file == PDF_PATH
    assert isinstance(result.invoice, Invoice)


def test_invoice_fails_business_validation(monkeypatch):
    """Test that an invalid invoice is retained with validation errors."""

    invoice = make_valid_invoice()

    # Create an invoice with an incorrect subtotal.
    invalid_invoice = invoice.model_copy(
        update={
            "subtotal": Decimal("530000.00")
        }
    )

    # Replace the AI extractor with the invalid invoice.
    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda invoice_text: invalid_invoice,
    )

    result = pipeline.process_invoice(PDF_PATH)

    assert isinstance(result, InvoiceProcessingResult)
    assert result.success is False
    assert result.invoice is not None
    assert result.invoice.subtotal == Decimal("530000.00")

    assert (
        "Invoice subtotal does not match line item amounts."
        in result.errors
    )

    assert result.source_file == PDF_PATH


# --------------------------------------------------
# GROUP 1: BUSINESS VALIDATION FAILURES
# --------------------------------------------------

def test_incorrect_line_item_amount(monkeypatch):
    invoice = make_valid_invoice()

    incorrect_item = invoice.line_items[0].model_copy(
        update={"amount": Decimal("369000.00")}
    )

    invalid_invoice = invoice.model_copy(
        update={
            "line_items": [
                incorrect_item,
                *invoice.line_items[1:],
            ]
        }
    )

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invalid_invoice,
    )

    result = pipeline.process_invoice(PDF_PATH)

    assert result.success is False
    assert (
        "One or more line items have incorrect amounts."
        in result.errors
    )


def test_incorrect_invoice_total(monkeypatch):
    invoice = make_valid_invoice()

    invalid_invoice = invoice.model_copy(
        update={"total_amount": Decimal("570000.00")}
    )

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invalid_invoice,
    )

    result = pipeline.process_invoice(PDF_PATH)

    assert result.success is False
    assert (
        "Invoice total does not match subtotal plus tax."
        in result.errors
    )


def test_invalid_due_date(monkeypatch):
    invoice = make_valid_invoice()

    invalid_invoice = invoice.model_copy(
        update={"due_date": date(2026, 10, 20)}
    )

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invalid_invoice,
    )

    result = pipeline.process_invoice(PDF_PATH)

    assert result.success is False
    assert (
        "Due date cannot be earlier than invoice date."
        in result.errors
    )


def test_duplicate_invoice_rejected(monkeypatch):
    invoice = make_valid_invoice()
    existing_invoice = make_valid_invoice()

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )

    result = pipeline.process_invoice(
        PDF_PATH,
        existing_invoices=[existing_invoice],
    )

    assert result.success is False
    assert "Duplicate invoice detected." in result.errors


def test_multiple_validation_errors_reported(monkeypatch):
    invoice = make_valid_invoice()

    incorrect_item = invoice.line_items[0].model_copy(
        update={"amount": Decimal("369000.00")}
    )

    invalid_invoice = invoice.model_copy(
        update={
            "line_items": [
                incorrect_item,
                *invoice.line_items[1:],
            ],
            "total_amount": Decimal("570000.00"),
            "due_date": date(2026, 10, 20),
        }
    )

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invalid_invoice,
    )

    result = pipeline.process_invoice(PDF_PATH)

    assert result.success is False
    assert len(result.errors) == 4

    assert (
        "One or more line items have incorrect amounts."
        in result.errors
    )
    assert (
        "Invoice subtotal does not match line item amounts."
        in result.errors
    )
    assert (
        "Invoice total does not match subtotal plus tax."
        in result.errors
    )
    assert (
        "Due date cannot be earlier than invoice date."
        in result.errors
    )


# --------------------------------------------------
# GROUP 2: EXISTING INVOICE HANDLING
# --------------------------------------------------

def test_process_invoice_without_existing_invoices(monkeypatch):
    invoice = make_valid_invoice()

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )

    result = pipeline.process_invoice(PDF_PATH)

    assert result.success is True
    assert result.errors == []
    assert result.invoice == invoice


def test_existing_invoices_are_used_for_duplicate_check(monkeypatch):
    invoice = make_valid_invoice()
    existing_invoice = make_valid_invoice()

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )

    result = pipeline.process_invoice(
        PDF_PATH,
        existing_invoices=[existing_invoice],
    )

    assert result.success is False
    assert "Duplicate invoice detected." in result.errors


def test_invoice_retained_after_validation_failure(monkeypatch):
    invoice = make_valid_invoice()

    invalid_invoice = invoice.model_copy(
        update={"subtotal": Decimal("530000.00")}
    )

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invalid_invoice,
    )

    result = pipeline.process_invoice(PDF_PATH)

    assert result.success is False
    assert result.invoice is not None
    assert isinstance(result.invoice, Invoice)
    assert result.invoice.subtotal == Decimal("530000.00")
    assert result.source_file == PDF_PATH


# --------------------------------------------------
# GROUP 3: PIPELINE DEPENDENCY TESTS
# --------------------------------------------------

def test_pdf_extraction_function_is_called(monkeypatch):
    invoice = make_valid_invoice()

    calls = {"pdf_extractor": False}

    def mock_pdf_extractor(pdf_path):
        calls["pdf_extractor"] = True
        return "Fictional invoice text"

    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        mock_pdf_extractor,
    )

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )

    result = pipeline.process_invoice(PDF_PATH)

    assert calls["pdf_extractor"] is True
    assert result.success is True


def test_extracted_pdf_text_is_passed_to_ai_extractor(monkeypatch):
    invoice = make_valid_invoice()

    expected_text = "NovaTech Office Solutions Invoice INV-2026-1048"
    received_text = {"value": None}

    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        lambda pdf_path: expected_text,
    )

    def mock_ai_extractor(invoice_text):
        received_text["value"] = invoice_text
        return invoice

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        mock_ai_extractor,
    )

    result = pipeline.process_invoice(PDF_PATH)

    assert received_text["value"] == expected_text
    assert result.success is True


# --------------------------------------------------
# GROUP 4: EXTRACTION FAILURE TESTS
# --------------------------------------------------

def test_pdf_extraction_exception_propagates(monkeypatch):
    def mock_pdf_extractor(pdf_path):
        raise FileNotFoundError("Invoice PDF not found.")

    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        mock_pdf_extractor,
    )

    with pytest.raises(
        FileNotFoundError,
        match="Invoice PDF not found.",
    ):
        pipeline.process_invoice(PDF_PATH)


def test_ai_extraction_exception_propagates(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        lambda pdf_path: "Fictional invoice text",
    )

    def mock_ai_extractor(invoice_text):
        raise RuntimeError("AI extraction failed.")

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        mock_ai_extractor,
    )

    with pytest.raises(
        RuntimeError,
        match="AI extraction failed.",
    ):
        pipeline.process_invoice(PDF_PATH)
