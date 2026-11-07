import pytest
from datetime import date
from decimal import Decimal
from src import pipeline
from src.schemas import Invoice, InvoiceProcessingResult
from src.quickbooks import create_bill_draft
from src.logging_config import configure_logging

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

    monkeypatch.setattr(
        pipeline.storage,
        "save_invoice_and_quickbooks_draft",
        lambda invoice, source_file, draft: (1, 1),
    )

@pytest.fixture
def isolated_invoice_log(tmp_path):
    """Create an isolated log file for pipeline logging tests."""

    log_file = tmp_path / "processing.log"
    logger = configure_logging(log_file=log_file)

    yield logger, log_file

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

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
    """A successfully validated invoice should be saved atomically once."""

    invoice = make_valid_invoice()
    save_calls = []

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "save_invoice_and_quickbooks_draft",
        lambda invoice, source_file, draft: (
            save_calls.append((invoice, source_file, draft)) or (1, 1)
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


def test_atomic_save_receives_correct_invoice_and_pdf_path(monkeypatch):
    """Atomic storage should receive the extracted invoice and original PDF path."""

    invoice = make_valid_invoice()
    save_calls = []

    def mock_atomic_save(invoice, source_file, draft):
        save_calls.append((invoice, source_file, draft))
        return 1, 1

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "save_invoice_and_quickbooks_draft",
        mock_atomic_save,
    )

    pipeline.process_invoice(
        PDF_PATH,
        existing_invoices=[],
    )

    assert len(save_calls) == 1
    assert save_calls[0][0] is invoice
    assert save_calls[0][1] == PDF_PATH
    assert save_calls[0][2].bill_number == invoice.invoice_number

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
    """A valid invoice should be transformed into a QuickBooks bill draft."""

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

    def mock_atomic_save(invoice, source_file, draft):
        saved_drafts.append(draft)
        return 1, 1

    monkeypatch.setattr(
        pipeline.storage,
        "save_invoice_and_quickbooks_draft",
        mock_atomic_save,
    )

    result = pipeline.process_invoice(
        "invoice.pdf",
        existing_invoices=[],
    )

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


def test_process_invoice_saves_invoice_and_draft_atomically(
    monkeypatch,
):
    """The invoice and its QuickBooks draft should be saved in one operation."""

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

    def mock_atomic_save(invoice, source_file, draft):
        operations.append({
            "invoice": invoice,
            "source_file": source_file,
            "draft": draft,
        })
        return 1, 1

    monkeypatch.setattr(
        pipeline.storage,
        "save_invoice_and_quickbooks_draft",
        mock_atomic_save,
    )

    pipeline.process_invoice(
        "invoice.pdf",
        existing_invoices=[],
    )

    assert len(operations) == 1
    assert operations[0]["invoice"] is invoice
    assert operations[0]["source_file"] == "invoice.pdf"
    assert operations[0]["draft"].bill_number == invoice.invoice_number

def test_recent_email_is_marked_processed_after_all_pdfs_succeed(
    monkeypatch,
):
    email = {
        "message_id": "test-email-success-001",
        "subject": "Invoice Submission",
        "downloaded_files": [
            "invoice_one.pdf",
            "invoice_two.pdf",
        ],
    }

    message_id = email["message_id"]

    processed_files = []
    marked_processed = []
    marked_failed = []
    marked_attachments_processed = []

    attachment_records = [
        {
            "message_id": message_id,
            "part_id": "part-one",
            "filename": "invoice_one.pdf",
            "file_path": "invoice_one.pdf",
            "status": "downloaded",
            "error_message": None,
        },
        {
            "message_id": message_id,
            "part_id": "part-two",
            "filename": "invoice_two.pdf",
            "file_path": "invoice_two.pdf",
            "status": "downloaded",
            "error_message": None,
        },
    ]

    monkeypatch.setattr(
        pipeline,
        "ingest_recent_invoice_emails",
        lambda **kwargs: [email],
    )

    def mock_process_invoice(pdf_path):
        processed_files.append(str(pdf_path))

        return InvoiceProcessingResult(
            success=True,
            invoice=make_valid_invoice(),
            errors=[],
            source_file=str(pdf_path),
        )

    monkeypatch.setattr(
        pipeline,
        "process_invoice",
        mock_process_invoice,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "get_email_attachments",
        lambda message_id: attachment_records,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "should_process_attachment",
        lambda message_id, part_id: True,
    )

    def mock_mark_attachment_processed(message_id, part_id):
        marked_attachments_processed.append((message_id, part_id))

        for record in attachment_records:
            if record["part_id"] == part_id:
                record["status"] = "processed"

    monkeypatch.setattr(
        pipeline.storage,
        "mark_attachment_processed",
        mock_mark_attachment_processed,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_attachment_failed",
        lambda message_id, part_id, error: pytest.fail(
            "A successful attachment must not be marked failed."
        ),
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_email_processed",
        lambda message_id: marked_processed.append(message_id),
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_email_failed",
        lambda message_id, error: marked_failed.append(message_id),
    )

    results = pipeline.process_recent_invoice_emails()

    assert len(processed_files) == 2

    assert results[0]["status"] == "processed"

    assert results[0]["processed_files"] == [
        "invoice_one.pdf",
        "invoice_two.pdf",
    ]

    assert results[0]["skipped_files"] == []

    assert marked_attachments_processed == [
        (message_id, "part-one"),
        (message_id, "part-two"),
    ]

    assert marked_processed == [message_id]
    assert marked_failed == []

def test_recent_email_is_marked_failed_when_invoice_validation_fails(
    monkeypatch,
):
    email = {
        "message_id": "test-email-failure-001",
        "subject": "Invoice Submission",
        "downloaded_files": ["invalid_invoice.pdf"],
    }

    marked_processed = []
    marked_failed = []

    monkeypatch.setattr(
        pipeline,
        "ingest_recent_invoice_emails",
        lambda **kwargs: [email],
    )

    monkeypatch.setattr(
        pipeline,
        "process_invoice",
        lambda pdf_path: InvoiceProcessingResult(
            success=False,
            invoice=make_valid_invoice(),
            errors=["Invoice total does not match subtotal plus tax."],
            source_file=str(pdf_path),
        ),
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_email_processed",
        lambda message_id: marked_processed.append(message_id),
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_email_failed",
        lambda message_id, error, failure_type="transient": marked_failed.append(
            (message_id, error, failure_type)
        ),
    )

    results = pipeline.process_recent_invoice_emails()

    assert results[0]["status"] == "failed"
    assert results[0]["errors"]
    assert marked_processed == []
    assert marked_failed[0][0] == "test-email-failure-001"


def test_recent_email_is_marked_failed_when_processing_raises_exception(
    monkeypatch,
):
    email = {
        "message_id": "test-email-exception-001",
        "subject": "Invoice Submission",
        "downloaded_files": ["invoice.pdf"],
    }

    message_id = email["message_id"]

    marked_failed = []
    marked_attachment_failed = []

    attachment_records = [
        {
            "message_id": message_id,
            "part_id": "exception-part",
            "filename": "invoice.pdf",
            "file_path": "invoice.pdf",
            "status": "downloaded",
            "error_message": None,
        },
    ]

    monkeypatch.setattr(
        pipeline,
        "ingest_recent_invoice_emails",
        lambda **kwargs: [email],
    )

    def mock_process_invoice(pdf_path):
        raise RuntimeError("AI extraction service unavailable.")

    monkeypatch.setattr(
        pipeline,
        "process_invoice",
        mock_process_invoice,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "get_email_attachments",
        lambda message_id: attachment_records,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "should_process_attachment",
        lambda message_id, part_id: True,
    )

    def mock_mark_attachment_failed(
        message_id,
        part_id,
        error,
        failure_type="transient",
    ):
        marked_attachment_failed.append(
            (message_id, part_id, error, failure_type)
        )

        for record in attachment_records:
            if record["part_id"] == part_id:
                record["status"] = "failed"
                record["error_message"] = error
                record["failure_type"] = failure_type
                record["retry_count"] = record.get("retry_count", 0) + 1

    monkeypatch.setattr(
        pipeline.storage,
        "mark_attachment_failed",
        mock_mark_attachment_failed,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_attachment_processed",
        lambda message_id, part_id: pytest.fail(
            "A failed attachment must not be marked processed."
        ),
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_email_processed",
        lambda message_id: pytest.fail(
            "A failed email must not be marked processed."
        ),
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_email_failed",
        lambda message_id, error, failure_type="transient": marked_failed.append(
            (message_id, error, failure_type)
        ),
    )

    results = pipeline.process_recent_invoice_emails()

    assert results[0]["status"] == "failed"

    assert (
        "AI extraction service unavailable."
        in results[0]["errors"][0]
    )

    assert len(marked_attachment_failed) == 1
    assert marked_attachment_failed[0][0] == message_id
    assert marked_attachment_failed[0][1] == "exception-part"

    assert marked_failed[0][0] == message_id
    assert (
        "AI extraction service unavailable."
        in marked_failed[0][1]
    )


def test_retry_skips_successful_attachments_and_retries_failed_one(
    monkeypatch,
):
    message_id = "partial-failure-email-001"

    email = {
        "message_id": message_id,
        "subject": "Invoice Submission",
        "downloaded_files": [
            "invoice_one.pdf",
            "invoice_two.pdf",
            "invoice_three.pdf",
        ],
    }

    attachment_records = [
        {
            "message_id": message_id,
            "part_id": "part-one",
            "filename": "invoice_one.pdf",
            "file_path": "invoice_one.pdf",
            "status": "downloaded",
            "error_message": None,
        },
        {
            "message_id": message_id,
            "part_id": "part-two",
            "filename": "invoice_two.pdf",
            "file_path": "invoice_two.pdf",
            "status": "downloaded",
            "error_message": None,
        },
        {
            "message_id": message_id,
            "part_id": "part-three",
            "filename": "invoice_three.pdf",
            "file_path": "invoice_three.pdf",
            "status": "downloaded",
            "error_message": None,
        },
    ]

    process_attempts = []
    marked_email_processed = []
    marked_email_failed = []

    # Simulate ingestion returning the same email on every attempt.
    monkeypatch.setattr(
        pipeline,
        "ingest_recent_invoice_emails",
        lambda **kwargs: [email],
    )

    monkeypatch.setattr(
        pipeline.storage,
        "get_email_attachments",
        lambda message_id: attachment_records,
    )

    # An attachment can be processed unless it is already processed.
    monkeypatch.setattr(
        pipeline.storage,
        "should_process_attachment",
        lambda message_id, part_id: next(
            record["status"] != "processed"
            for record in attachment_records
            if record["part_id"] == part_id
        ),
    )

    def mock_process_invoice(pdf_path):
        filename = str(pdf_path)
        process_attempts.append(filename)

        # Simulate an AI extraction failure on the third attachment
        # during the first attempt only.
        if (
            filename == "invoice_three.pdf"
            and process_attempts.count(filename) == 1
        ):
            raise RuntimeError("AI extraction service unavailable.")

        return InvoiceProcessingResult(
            success=True,
            invoice=make_valid_invoice(),
            errors=[],
            source_file=filename,
        )

    monkeypatch.setattr(
        pipeline,
        "process_invoice",
        mock_process_invoice,
    )

    def mock_mark_attachment_processed(message_id, part_id):
        for record in attachment_records:
            if record["part_id"] == part_id:
                record["status"] = "processed"
                record["error_message"] = None

    monkeypatch.setattr(
        pipeline.storage,
        "mark_attachment_processed",
        mock_mark_attachment_processed,
    )

    def mock_mark_attachment_failed(
        message_id,
        part_id,
        error,
        failure_type="transient",
    ):
        for record in attachment_records:
            if record["part_id"] == part_id:
                record["status"] = "failed"
                record["error_message"] = error
                record["failure_type"] = failure_type
                record["retry_count"] = record.get("retry_count", 0) + 1

    monkeypatch.setattr(
        pipeline.storage,
        "mark_attachment_failed",
        mock_mark_attachment_failed,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_email_processed",
        lambda message_id: marked_email_processed.append(message_id),
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_email_failed",
        lambda message_id, error, failure_type="transient": marked_email_failed.append(
            (message_id, error, failure_type)
        ),
    )

    # First attempt: two attachments succeed and the third fails.
    first_results = pipeline.process_recent_invoice_emails()

    assert first_results[0]["status"] == "failed"

    assert first_results[0]["processed_files"] == [
        "invoice_one.pdf",
        "invoice_two.pdf",
    ]

    assert first_results[0]["skipped_files"] == []

    assert [
        record["status"] for record in attachment_records
    ] == [
        "processed",
        "processed",
        "failed",
    ]

    assert len(process_attempts) == 3

    # Second attempt: only the previously failed attachment is retried.
    second_results = pipeline.process_recent_invoice_emails()

    assert second_results[0]["status"] == "processed"

    assert second_results[0]["processed_files"] == [
        "invoice_three.pdf",
    ]

    assert second_results[0]["skipped_files"] == [
        "invoice_one.pdf",
        "invoice_two.pdf",
    ]

    # The first two attachments must not have been processed again.
    assert process_attempts == [
        "invoice_one.pdf",
        "invoice_two.pdf",
        "invoice_three.pdf",
        "invoice_three.pdf",
    ]

    assert [
        record["status"] for record in attachment_records
    ] == [
        "processed",
        "processed",
        "processed",
    ]

    assert marked_email_processed == [message_id]

    assert len(marked_email_failed) == 1
    assert marked_email_failed[0][0] == message_id

def test_process_invoice_saves_invoice_and_draft_atomically(
    monkeypatch,
):
    calls = []

    def mock_atomic_save(invoice, source_file, draft):
        calls.append({
            "invoice": invoice,
            "source_file": source_file,
            "draft": draft,
        })
        return 1, 1

    monkeypatch.setattr(
        pipeline.storage,
        "save_invoice_and_quickbooks_draft",
        mock_atomic_save,
    )

    # Keep the rest of this test consistent with your existing
    # successful process_invoice test setup.

def test_invoice_processing_logs_do_not_expose_invoice_details(
    monkeypatch,
    isolated_invoice_log,
):
    logger, log_file = isolated_invoice_log

    invoice = make_valid_invoice()

    sensitive_pdf_text = (
        "PRIVATE_RAW_INVOICE_TEXT_12345"
    )

    monkeypatch.setattr(
        pipeline,
        "extract_text_from_pdf",
        lambda path: sensitive_pdf_text,
    )

    monkeypatch.setattr(
        pipeline,
        "extract_invoice_data",
        lambda text: invoice,
    )

    result = pipeline.process_invoice(
        PDF_PATH,
        existing_invoices=[],
    )

    assert result.success is True

    for handler in logger.handlers:
        handler.flush()

    log_contents = log_file.read_text(encoding="utf-8")

    # Expected operational messages should be present.
    assert "Invoice processing started" in log_contents
    assert "PDF text extraction completed" in log_contents
    assert "AI invoice extraction completed" in log_contents
    assert "Invoice validation passed" in log_contents
    assert "saved successfully" in log_contents

    # Sensitive invoice information must not appear.
    assert sensitive_pdf_text not in log_contents
    assert invoice.vendor_name not in log_contents
    assert invoice.customer_name not in log_contents
    assert invoice.invoice_number not in log_contents

def test_email_processing_logs_do_not_expose_sensitive_details(
    monkeypatch,
    tmp_path,
    isolated_invoice_log,
):
    logger, log_file = isolated_invoice_log

    message_id = "PRIVATE_MESSAGE_ID_12345"
    subject = "CONFIDENTIAL_EMAIL_SUBJECT"
    attachment_path = tmp_path / "CONFIDENTIAL_INVOICE_PATH.pdf"
    exception_message = "PRIVATE_EXCEPTION_DETAILS_98765"

    email = {
        "message_id": message_id,
        "subject": subject,
        "downloaded_files": [str(attachment_path)],
    }

    attachment_records = [
        {
            "message_id": message_id,
            "part_id": "private-part-001",
            "filename": "invoice.pdf",
            "file_path": str(attachment_path),
            "status": "downloaded",
            "error_message": None,
        }
    ]

    monkeypatch.setattr(
        pipeline,
        "ingest_recent_invoice_emails",
        lambda **kwargs: [email],
    )

    monkeypatch.setattr(
        pipeline.storage,
        "get_email_attachments",
        lambda message_id: attachment_records,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "should_process_attachment",
        lambda message_id, part_id: True,
    )

    def mock_process_invoice(pdf_path):
        raise RuntimeError(exception_message)

    monkeypatch.setattr(
        pipeline,
        "process_invoice",
        mock_process_invoice,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_attachment_failed",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        pipeline.storage,
        "mark_email_failed",
        lambda *args, **kwargs: None,
    )

    results = pipeline.process_recent_invoice_emails()

    assert results[0]["status"] == "failed"

    for handler in logger.handlers:
        handler.flush()

    log_contents = log_file.read_text(encoding="utf-8")

    # Operational information should be logged.
    assert "Email ingestion completed" in log_contents
    assert "Attachment processing failed" in log_contents
    assert "RuntimeError" in log_contents

    # Sensitive information must not appear.
    assert message_id not in log_contents
    assert subject not in log_contents
    assert str(attachment_path) not in log_contents
    assert exception_message not in log_contents

