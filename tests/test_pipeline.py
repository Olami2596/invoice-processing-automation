import pytest
from datetime import date
from decimal import Decimal
from src import pipeline
from src.schemas import Invoice, InvoiceProcessingResult
from src.quickbooks import create_bill_draft


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


@pytest.fixture(autouse=True)
def isolate_pipeline_storage(monkeypatch):
    """Prevent pipeline tests from accessing the real invoice database."""

    # Return an empty database result by default.
    monkeypatch.setattr(
        pipeline,
        "get_all_invoices",
        lambda: [],
    )

    # Prevent tests from inserting records into the real invoice database.
    monkeypatch.setattr(
        pipeline,
        "save_invoice",
        lambda invoice, source_file: 1,
    )

    # Prevent tests from inserting records into the real QuickBooks database.
    monkeypatch.setattr(
        pipeline,
        "save_quickbooks_draft",
        lambda draft: 1,
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


def test_process_invoice_loads_existing_invoices_when_omitted(
    monkeypatch,
):
    """The pipeline should retrieve existing invoices when none are supplied."""

    invoice = make_valid_invoice()
    existing_invoices = [make_valid_invoice()]

    get_all_invoices_calls = []

    def mock_get_all_invoices():
        get_all_invoices_calls.append(True)
        return existing_invoices

    monkeypatch.setattr(
        pipeline,
        "get_all_invoices",
        mock_get_all_invoices,
        raising=False,
    )
    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        lambda pdf_path: "Extracted invoice text",
    )
    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda invoice_text: invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "validate_invoice",
        lambda invoice, existing: [],
    )

    pipeline.process_invoice("data/fictional_invoice.pdf")

    assert len(get_all_invoices_calls) == 1


def test_process_invoice_passes_database_invoices_to_validation(
    monkeypatch,
):
    """Invoices retrieved from storage should be passed to validate_invoice."""

    invoice = make_valid_invoice()
    existing_invoices = [make_valid_invoice()]

    captured_invoices = {}

    monkeypatch.setattr(
        pipeline,
        "get_all_invoices",
        lambda: existing_invoices,
        raising=False,
    )
    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        lambda pdf_path: "Extracted invoice text",
    )
    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda invoice_text: invoice,
    )

    def mock_validate_invoice(invoice, existing):
        captured_invoices["existing"] = existing
        return []

    monkeypatch.setattr(
        pipeline,
        "validate_invoice",
        mock_validate_invoice,
    )

    pipeline.process_invoice("data/fictional_invoice.pdf")

    assert captured_invoices["existing"] is existing_invoices


def test_process_invoice_does_not_load_database_when_existing_invoices_supplied(
    monkeypatch,
):
    """Explicitly supplied invoices should prevent database retrieval."""

    invoice = make_valid_invoice()
    existing_invoices = [make_valid_invoice()]

    def unexpected_database_call():
        pytest.fail("get_all_invoices() should not have been called.")

    monkeypatch.setattr(
        pipeline,
        "get_all_invoices",
        unexpected_database_call,
        raising=False,
    )
    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        lambda pdf_path: "Extracted invoice text",
    )
    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda invoice_text: invoice,
    )

    captured_invoices = {}

    def mock_validate_invoice(invoice, existing):
        captured_invoices["existing"] = existing
        return []

    monkeypatch.setattr(
        pipeline,
        "validate_invoice",
        mock_validate_invoice,
    )

    pipeline.process_invoice(
        "data/fictional_invoice.pdf",
        existing_invoices=existing_invoices,
    )

    assert captured_invoices["existing"] is existing_invoices



def test_process_invoice_respects_explicit_empty_existing_invoices(
    monkeypatch,
):
    """An explicitly supplied empty list should not trigger database retrieval."""

    invoice = make_valid_invoice()
    empty_existing_invoices = []

    def unexpected_database_call():
        pytest.fail("get_all_invoices() should not have been called.")

    monkeypatch.setattr(
        pipeline,
        "get_all_invoices",
        unexpected_database_call,
        raising=False,
    )
    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        lambda pdf_path: "Extracted invoice text",
    )
    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda invoice_text: invoice,
    )

    captured_invoices = {}

    def mock_validate_invoice(invoice, existing):
        captured_invoices["existing"] = existing
        return []

    monkeypatch.setattr(
        pipeline,
        "validate_invoice",
        mock_validate_invoice,
    )

    pipeline.process_invoice(
        "data/fictional_invoice.pdf",
        existing_invoices=empty_existing_invoices,
    )

    assert captured_invoices["existing"] is empty_existing_invoices
    assert captured_invoices["existing"] == []


def test_valid_invoice_is_saved_once(monkeypatch):
    """A successfully validated invoice should be saved exactly once."""

    invoice = make_valid_invoice()
    save_calls = []

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "save_invoice",
        lambda invoice, source_file: save_calls.append(
            (invoice, source_file)
        ),
    )

    result = pipeline.process_invoice(
        PDF_PATH,
        existing_invoices=[],
    )

    assert result.success is True
    assert len(save_calls) == 1


def test_invalid_invoice_is_not_saved(monkeypatch):
    """An invoice that fails validation should not be saved."""

    invoice = make_valid_invoice().model_copy(
        update={"total_amount": Decimal("570000.00")}
    )

    save_calls = []

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "save_invoice",
        lambda invoice, source_file: save_calls.append(
            (invoice, source_file)
        ),
    )

    result = pipeline.process_invoice(
        PDF_PATH,
        existing_invoices=[],
    )

    assert result.success is False
    assert result.errors
    assert save_calls == []


def test_duplicate_invoice_is_not_saved(monkeypatch):
    """A duplicate invoice should fail validation and not be saved."""

    invoice = make_valid_invoice()
    existing_invoices = [make_valid_invoice()]

    save_calls = []

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "save_invoice",
        lambda invoice, source_file: save_calls.append(
            (invoice, source_file)
        ),
    )

    result = pipeline.process_invoice(
        PDF_PATH,
        existing_invoices=existing_invoices,
    )

    assert result.success is False
    assert "Duplicate invoice detected." in result.errors
    assert save_calls == []


def test_save_invoice_receives_correct_invoice_and_pdf_path(
    monkeypatch,
):
    """save_invoice should receive the extracted invoice and original PDF path."""

    invoice = make_valid_invoice()
    save_calls = []

    def mock_save_invoice(saved_invoice, source_file):
        save_calls.append((saved_invoice, source_file))
        return 1

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "save_invoice",
        mock_save_invoice,
    )

    pipeline.process_invoice(
        PDF_PATH,
        existing_invoices=[],
    )

    assert len(save_calls) == 1
    assert save_calls[0][0] is invoice
    assert save_calls[0][1] == PDF_PATH


def test_explicit_existing_invoices_are_respected(
    monkeypatch,
):
    """Explicitly supplied invoices should be used instead of database records."""

    invoice = make_valid_invoice()
    explicit_invoices = [
        make_valid_invoice().model_copy(
            update={"invoice_number": "INV-2026-2000"}
        )
    ]

    captured = {}

    def unexpected_database_call():
        pytest.fail("Database retrieval should not occur.")

    def mock_validate_invoice(invoice, existing_invoices):
        captured["existing_invoices"] = existing_invoices
        return []

    monkeypatch.setattr(
        pipeline,
        "get_all_invoices",
        unexpected_database_call,
    )
    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "validate_invoice",
        mock_validate_invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "save_invoice",
        lambda invoice, source_file: 1,
    )

    result = pipeline.process_invoice(
        PDF_PATH,
        existing_invoices=explicit_invoices,
    )

    assert result.success is True
    assert captured["existing_invoices"] is explicit_invoices


def test_database_invoices_are_retrieved_when_existing_invoices_omitted(
    monkeypatch,
):
    """The pipeline should retrieve and use stored invoices when none are supplied."""

    invoice = make_valid_invoice()
    database_invoices = [
        make_valid_invoice().model_copy(
            update={"invoice_number": "INV-2026-2000"}
        )
    ]

    retrieval_calls = []
    captured = {}

    def mock_get_all_invoices():
        retrieval_calls.append(True)
        return database_invoices

    def mock_validate_invoice(invoice, existing_invoices):
        captured["existing_invoices"] = existing_invoices
        return []

    monkeypatch.setattr(
        pipeline,
        "get_all_invoices",
        mock_get_all_invoices,
    )
    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "validate_invoice",
        mock_validate_invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "save_invoice",
        lambda invoice, source_file: 1,
    )

    result = pipeline.process_invoice(PDF_PATH)

    assert result.success is True
    assert len(retrieval_calls) == 1
    assert captured["existing_invoices"] is database_invoices


def test_process_invoice_creates_quickbooks_draft(monkeypatch):
    """A valid invoice should be transformed into a bill draft."""

    invoice = make_valid_invoice()
    saved_drafts = []

    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        lambda path: "invoice text",
    )
    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "get_all_invoices",
        lambda: [],
    )
    monkeypatch.setattr(
        pipeline,
        "save_invoice",
        lambda invoice, path: 1,
    )
    monkeypatch.setattr(
        pipeline,
        "save_quickbooks_draft",
        lambda draft: saved_drafts.append(draft),
    )

    result = pipeline.process_invoice("invoice.pdf")

    assert result.success is True
    assert len(saved_drafts) == 1
    assert saved_drafts[0].vendor_name == invoice.vendor_name
    assert saved_drafts[0].bill_number == invoice.invoice_number
    assert saved_drafts[0].status == "draft"


def test_process_invoice_does_not_create_draft_when_invalid(monkeypatch):
    """An invalid invoice must not produce an accounting draft."""

    invoice = make_valid_invoice()
    saved_drafts = []

    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        lambda path: "invoice text",
    )
    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "get_all_invoices",
        lambda: [invoice],
    )
    monkeypatch.setattr(
        pipeline,
        "save_invoice",
        lambda invoice, path: pytest.fail(
            "Invalid invoices must not be saved."
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "save_quickbooks_draft",
        lambda draft: saved_drafts.append(draft),
    )

    result = pipeline.process_invoice("invoice.pdf")

    assert result.success is False
    assert saved_drafts == []


def test_process_invoice_saves_original_invoice_before_draft(
    monkeypatch,
):
    """The original invoice should be saved before its draft."""

    invoice = make_valid_invoice()
    operations = []

    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        lambda path: "invoice text",
    )
    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )
    monkeypatch.setattr(
        pipeline,
        "get_all_invoices",
        lambda: [],
    )
    monkeypatch.setattr(
        pipeline,
        "save_invoice",
        lambda invoice, path: operations.append("invoice"),
    )
    monkeypatch.setattr(
        pipeline,
        "save_quickbooks_draft",
        lambda draft: operations.append("draft"),
    )

    pipeline.process_invoice("invoice.pdf")

    assert operations == ["invoice", "draft"]
