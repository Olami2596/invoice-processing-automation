import json
import pytest
import sqlite3
import src.storage as storage
from datetime import date
from decimal import Decimal
from src.schemas import Invoice, InvoiceLineItem, QuickBooksBillDraft, QuickBooksBillLineItem

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Create an isolated temporary database for each test."""

    db_path = tmp_path / "test_invoices.db"

    def get_test_connection():
        return sqlite3.connect(db_path)

    monkeypatch.setattr(storage, "get_connection", get_test_connection)

    storage.initialise_database()

    return db_path


def make_invoice(
    due_date=date(2026, 11, 10),
    tax_amount=Decimal("39375.00"),
):
    """Create a valid invoice for storage tests."""

    return Invoice(
        vendor_name="NovaTech Office Solutions",
        customer_name="BrightPath Creative Studio",
        invoice_number="INV-2026-1048",
        invoice_date=date(2026, 10, 27),
        due_date=due_date,
        currency="NGN",
        line_items=[
            InvoiceLineItem(
                description="Laptop setup and configuration",
                quantity=Decimal("2"),
                unit_price=Decimal("185000.00"),
                amount=Decimal("370000.00"),
            ),
            InvoiceLineItem(
                description="Network installation",
                quantity=Decimal("1"),
                unit_price=Decimal("95000.00"),
                amount=Decimal("95000.00"),
            ),
            InvoiceLineItem(
                description="Cloud backup configuration",
                quantity=Decimal("1"),
                unit_price=Decimal("60000.00"),
                amount=Decimal("60000.00"),
            ),
        ],
        subtotal=Decimal("525000.00"),
        tax_amount=tax_amount,
        total_amount=Decimal("564375.00")
        if tax_amount is not None
        else Decimal("525000.00"),
    )


def test_save_invoice_returns_database_id(test_db):
    """Saving a valid invoice should return an integer database ID."""

    invoice = make_invoice()

    invoice_id = storage.save_invoice(
        invoice,
        "data/fictional_invoice.pdf",
    )

    assert isinstance(invoice_id, int)
    assert invoice_id > 0


def test_save_invoice_stores_invoice_in_database(test_db):
    """The saved invoice should exist in the database."""

    invoice = make_invoice()

    invoice_id = storage.save_invoice(
        invoice,
        "data/fictional_invoice.pdf",
    )

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT * FROM invoices WHERE id = ?",
            (invoice_id,),
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[1] == invoice.vendor_name
        assert row[2] == invoice.customer_name
        assert row[3] == invoice.invoice_number
    finally:
        connection.close()


def test_save_invoice_preserves_monetary_precision(test_db):
    """Monetary values should be stored as strings without precision loss."""

    invoice = make_invoice()

    invoice_id = storage.save_invoice(
        invoice,
        "data/fictional_invoice.pdf",
    )

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT subtotal, tax_amount, total_amount
            FROM invoices
            WHERE id = ?
            """,
            (invoice_id,),
        )

        row = cursor.fetchone()

        assert row == (
            "525000.00",
            "39375.00",
            "564375.00",
        )

        assert all(isinstance(value, str) for value in row)
    finally:
        connection.close()


def test_save_invoice_stores_line_items_as_valid_json(test_db):
    """Line items should be stored as valid JSON."""

    invoice = make_invoice()

    invoice_id = storage.save_invoice(
        invoice,
        "data/fictional_invoice.pdf",
    )

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT line_items FROM invoices WHERE id = ?",
            (invoice_id,),
        )

        stored_line_items = cursor.fetchone()[0]

        parsed_line_items = json.loads(stored_line_items)

        assert isinstance(parsed_line_items, list)
        assert len(parsed_line_items) == 3
        assert parsed_line_items[0]["description"] == (
            "Laptop setup and configuration"
        )
        assert parsed_line_items[0]["quantity"] == "2"
        assert parsed_line_items[0]["unit_price"] == "185000.00"
        assert parsed_line_items[0]["amount"] == "370000.00"
    finally:
        connection.close()


def test_save_invoice_stores_missing_optional_values_as_null(test_db):
    """Missing due_date and tax_amount should be stored as SQL NULL."""

    invoice = make_invoice(
        due_date=None,
        tax_amount=None,
    )

    invoice_id = storage.save_invoice(
        invoice,
        "data/fictional_invoice.pdf",
    )

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT due_date, tax_amount
            FROM invoices
            WHERE id = ?
            """,
            (invoice_id,),
        )

        row = cursor.fetchone()

        assert row == (None, None)
    finally:
        connection.close()


def test_save_invoice_rejects_duplicate_vendor_and_invoice_number(test_db):
    """The same vendor and invoice number combination must not be inserted twice."""

    invoice = make_invoice()

    storage.save_invoice(
        invoice,
        "data/fictional_invoice.pdf",
    )

    with pytest.raises(sqlite3.IntegrityError):
        storage.save_invoice(
            invoice,
            "data/fictional_invoice.pdf",
        )

def test_save_invoice_stores_source_file(test_db):
    """The original PDF path should be stored correctly."""

    invoice = make_invoice()
    source_file = "data/fictional_invoice.pdf"

    invoice_id = storage.save_invoice(
        invoice,
        source_file,
    )

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT source_file FROM invoices WHERE id = ?",
            (invoice_id,),
        )

        row = cursor.fetchone()

        assert row[0] == source_file

    finally:
        connection.close()


def test_get_all_invoices_returns_invoice_objects(test_db):
    """Retrieved records should be returned as Invoice objects."""

    invoice = make_invoice()

    storage.save_invoice(invoice, "data/fictional_invoice.pdf")

    invoices = storage.get_all_invoices()

    assert len(invoices) == 1
    assert isinstance(invoices[0], Invoice)


def test_get_all_invoices_restores_correct_data_types(test_db):
    """Retrieved invoice fields should have their correct Python types."""

    invoice = make_invoice()

    storage.save_invoice(invoice, "data/fictional_invoice.pdf")

    retrieved_invoice = storage.get_all_invoices()[0]

    assert isinstance(retrieved_invoice.invoice_date, date)
    assert isinstance(retrieved_invoice.due_date, date)
    assert isinstance(retrieved_invoice.subtotal, Decimal)
    assert isinstance(retrieved_invoice.tax_amount, Decimal)
    assert isinstance(retrieved_invoice.total_amount, Decimal)

    assert isinstance(retrieved_invoice.line_items, list)
    assert isinstance(retrieved_invoice.line_items[0], InvoiceLineItem)
    assert isinstance(retrieved_invoice.line_items[0].quantity, Decimal)
    assert isinstance(retrieved_invoice.line_items[0].unit_price, Decimal)


def test_get_all_invoices_preserves_invoice_values(test_db):
    """Retrieved invoice values should match the original invoice."""

    invoice = make_invoice()

    storage.save_invoice(invoice, "data/fictional_invoice.pdf")

    retrieved_invoice = storage.get_all_invoices()[0]

    assert retrieved_invoice.vendor_name == invoice.vendor_name
    assert retrieved_invoice.customer_name == invoice.customer_name
    assert retrieved_invoice.invoice_number == invoice.invoice_number
    assert retrieved_invoice.invoice_date == invoice.invoice_date
    assert retrieved_invoice.due_date == invoice.due_date
    assert retrieved_invoice.currency == invoice.currency
    assert retrieved_invoice.subtotal == invoice.subtotal
    assert retrieved_invoice.tax_amount == invoice.tax_amount
    assert retrieved_invoice.total_amount == invoice.total_amount
    assert retrieved_invoice.line_items == invoice.line_items


def test_get_all_invoices_returns_empty_list_when_database_is_empty(test_db):
    """An empty database should return an empty list."""

    invoices = storage.get_all_invoices()

    assert invoices == []


def test_get_all_invoices_restores_missing_optional_values(test_db):
    """SQL NULL values should be restored as Python None."""

    invoice = make_invoice(
        due_date=None,
        tax_amount=None,
    )

    storage.save_invoice(invoice, "data/fictional_invoice.pdf")

    retrieved_invoice = storage.get_all_invoices()[0]

    assert retrieved_invoice.due_date is None
    assert retrieved_invoice.tax_amount is None


def test_get_all_invoices_returns_in_insertion_order(test_db):
    """Invoices should be retrieved in their original insertion order."""

    first_invoice = make_invoice()
    second_invoice = make_invoice()

    second_invoice = second_invoice.model_copy(
        update={"invoice_number": "INV-2026-1049"}
    )

    storage.save_invoice(first_invoice, "first_invoice.pdf")
    storage.save_invoice(second_invoice, "second_invoice.pdf")

    invoices = storage.get_all_invoices()

    assert len(invoices) == 2
    assert invoices[0].invoice_number == "INV-2026-1048"
    assert invoices[1].invoice_number == "INV-2026-1049"


def make_quickbooks_draft(
    due_date=date(2026, 11, 10),
    tax_amount=Decimal("27750.00"),
):
    """Create a valid QuickBooks bill draft for storage tests."""

    return QuickBooksBillDraft(
        vendor_name="NovaTech Office Solutions",
        bill_number="INV-2026-1048",
        bill_date=date(2026, 10, 27),
        due_date=due_date,
        currency="NGN",
        line_items=[
            QuickBooksBillLineItem(
                description="Laptop setup and configuration",
                quantity=Decimal("2"),
                unit_price=Decimal("185000.00"),
                amount=Decimal("370000.00"),
            ),
        ],
        subtotal=Decimal("370000.00"),
        tax_amount=tax_amount,
        total_amount=(
            Decimal("397750.00")
            if tax_amount is not None
            else Decimal("370000.00")
        ),
    )


def test_save_quickbooks_draft_returns_database_id(test_db):
    """Saving a draft should return an integer database ID."""

    draft = make_quickbooks_draft()

    draft_id = storage.save_quickbooks_draft(draft)

    assert isinstance(draft_id, int)
    assert draft_id > 0


def test_save_quickbooks_draft_persists_record(test_db):
    """The saved draft should exist in the database."""

    draft = make_quickbooks_draft()

    draft_id = storage.save_quickbooks_draft(draft)

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT vendor_name, bill_number, status
            FROM quickbooks_bill_drafts
            WHERE id = ?
            """,
            (draft_id,),
        )

        row = cursor.fetchone()

        assert row == (
            "NovaTech Office Solutions",
            "INV-2026-1048",
            "draft",
        )

    finally:
        connection.close()


def test_save_quickbooks_draft_preserves_decimal_precision(test_db):
    """Financial values should be stored as precise decimal strings."""

    draft = make_quickbooks_draft()

    draft_id = storage.save_quickbooks_draft(draft)

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT subtotal, tax_amount, total_amount
            FROM quickbooks_bill_drafts
            WHERE id = ?
            """,
            (draft_id,),
        )

        row = cursor.fetchone()

        assert row == (
            "370000.00",
            "27750.00",
            "397750.00",
        )

    finally:
        connection.close()


def test_save_quickbooks_draft_stores_line_items_as_json(test_db):
    """Draft line items should be stored as valid JSON."""

    draft = make_quickbooks_draft()

    draft_id = storage.save_quickbooks_draft(draft)

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT line_items
            FROM quickbooks_bill_drafts
            WHERE id = ?
            """,
            (draft_id,),
        )

        stored_items = cursor.fetchone()[0]
        parsed_items = json.loads(stored_items)

        assert len(parsed_items) == 1
        assert parsed_items[0]["description"] == (
            "Laptop setup and configuration"
        )
        assert parsed_items[0]["quantity"] == "2"

    finally:
        connection.close()


def test_save_quickbooks_draft_stores_missing_optional_values(test_db):
    """Missing due date and tax should be stored as SQL NULL."""

    draft = make_quickbooks_draft(
        due_date=None,
        tax_amount=None,
    )

    draft_id = storage.save_quickbooks_draft(draft)

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT due_date, tax_amount
            FROM quickbooks_bill_drafts
            WHERE id = ?
            """,
            (draft_id,),
        )

        assert cursor.fetchone() == (None, None)

    finally:
        connection.close()


def test_save_quickbooks_draft_rejects_duplicates(test_db):
    """The same vendor and bill number cannot be inserted twice."""

    draft = make_quickbooks_draft()

    storage.save_quickbooks_draft(draft)

    with pytest.raises(sqlite3.IntegrityError):
        storage.save_quickbooks_draft(draft)


def test_get_all_quickbooks_drafts_returns_draft_objects(test_db):
    """Retrieved records should be QuickBooksBillDraft objects."""

    draft = make_quickbooks_draft()

    storage.save_quickbooks_draft(draft)

    drafts = storage.get_all_quickbooks_drafts()

    assert len(drafts) == 1
    assert isinstance(drafts[0], QuickBooksBillDraft)


def test_get_all_quickbooks_drafts_restores_correct_types(test_db):
    """Retrieved values should have their correct Python types."""

    draft = make_quickbooks_draft()

    storage.save_quickbooks_draft(draft)

    retrieved = storage.get_all_quickbooks_drafts()[0]

    assert isinstance(retrieved.bill_date, date)
    assert isinstance(retrieved.due_date, date)
    assert isinstance(retrieved.subtotal, Decimal)
    assert isinstance(retrieved.tax_amount, Decimal)
    assert isinstance(retrieved.total_amount, Decimal)
    assert isinstance(retrieved.line_items[0], QuickBooksBillLineItem)
    assert isinstance(retrieved.line_items[0].quantity, Decimal)


def test_get_all_quickbooks_drafts_preserves_original_values(test_db):
    """A retrieved draft should match the original draft."""

    draft = make_quickbooks_draft()

    storage.save_quickbooks_draft(draft)

    retrieved = storage.get_all_quickbooks_drafts()[0]

    assert retrieved.vendor_name == draft.vendor_name
    assert retrieved.bill_number == draft.bill_number
    assert retrieved.bill_date == draft.bill_date
    assert retrieved.due_date == draft.due_date
    assert retrieved.currency == draft.currency
    assert retrieved.line_items == draft.line_items
    assert retrieved.subtotal == draft.subtotal
    assert retrieved.tax_amount == draft.tax_amount
    assert retrieved.total_amount == draft.total_amount
    assert retrieved.status == "draft"


def test_get_all_quickbooks_drafts_returns_empty_list(test_db):
    """An empty draft table should return an empty list."""

    drafts = storage.get_all_quickbooks_drafts()

    assert drafts == []


def test_initialise_database_creates_all_tables(test_db):
    """Database initialisation should create all application tables."""

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
        """)

        table_names = {
            row[0] for row in cursor.fetchall()
        }

        assert "invoices" in table_names
        assert "quickbooks_bill_drafts" in table_names
        assert "email_processing" in table_names
        assert "email_attachments" in table_names
        assert "airtable_sync" in table_names

    finally:
        connection.close()


def test_airtable_sync_table_has_expected_columns(test_db):
    """The Airtable sync table should contain all required fields."""

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()

        cursor.execute("PRAGMA table_info(airtable_sync)")

        columns = {
            row[1] for row in cursor.fetchall()
        }

        expected_columns = {
            "id",
            "entity_type",
            "local_record_id",
            "airtable_record_id",
            "status",
            "retry_count",
            "error_message",
            "created_at",
            "updated_at",
        }

        assert expected_columns.issubset(columns)

    finally:
        connection.close()


def test_airtable_sync_table_initialization_is_idempotent(test_db):
    """Repeated initialization must not remove existing queue records."""

    connection = sqlite3.connect(test_db)

    try:
        connection.execute("""
            INSERT INTO airtable_sync (
                entity_type,
                local_record_id
            )
            VALUES ('invoice', 100)
        """)

        connection.commit()

    finally:
        connection.close()

    # Initialize the database again.
    storage.initialise_database()

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT entity_type, local_record_id, status
            FROM airtable_sync
        """)

        records = cursor.fetchall()

        assert records == [
            ("invoice", 100, "pending")
        ]

    finally:
        connection.close()

# --------------------------------------------------
# GROUP: EMAIL ATTACHMENT TRACKING
# --------------------------------------------------

def make_test_email(message_id="test-email-001"):
    """Register a test email for attachment tracking."""

    storage.register_email(
        message_id=message_id,
        subject="Invoice Submission - INV-TEST-001",
    )

    return message_id


def test_register_email_attachment_returns_true(test_db):
    """A new attachment should be registered successfully."""

    message_id = make_test_email()

    result = storage.register_email_attachment(
        message_id=message_id,
        part_id="part-001",
        filename="invoice.pdf",
    )

    assert result is True


def test_register_email_attachment_prevents_duplicates(test_db):
    """Registering the same attachment twice should not create duplicates."""

    message_id = make_test_email()

    first_result = storage.register_email_attachment(
        message_id=message_id,
        part_id="part-001",
        filename="invoice.pdf",
    )

    second_result = storage.register_email_attachment(
        message_id=message_id,
        part_id="part-001",
        filename="invoice.pdf",
    )

    assert first_result is True
    assert second_result is False


def test_get_email_attachment_record_returns_correct_data(test_db):
    """Attachment tracking records should be retrievable."""

    message_id = make_test_email()

    storage.register_email_attachment(
        message_id=message_id,
        part_id="part-001",
        filename="invoice.pdf",
    )

    record = storage.get_email_attachment_record(
        message_id,
        "part-001",
    )

    assert record is not None
    assert record["message_id"] == message_id
    assert record["part_id"] == "part-001"
    assert record["filename"] == "invoice.pdf"
    assert record["status"] == "pending"
    assert record["file_path"] is None
    assert record["error_message"] is None


def test_get_unknown_email_attachment_returns_none(test_db):
    """An unknown attachment should return None."""

    record = storage.get_email_attachment_record(
        "unknown-email",
        "unknown-part",
    )

    assert record is None


def test_mark_attachment_downloaded_stores_file_path(test_db):
    """A successful download should retain its file path."""

    message_id = make_test_email()

    storage.register_email_attachment(
        message_id=message_id,
        part_id="part-001",
        filename="invoice.pdf",
    )

    storage.mark_attachment_downloaded(
        message_id=message_id,
        part_id="part-001",
        file_path="data/email_attachments/invoice.pdf",
    )

    record = storage.get_email_attachment_record(
        message_id,
        "part-001",
    )

    assert record["status"] == "downloaded"
    assert record["file_path"] == (
        "data/email_attachments/invoice.pdf"
    )
    assert record["error_message"] is None


def test_mark_attachment_processed(test_db):
    """A successfully processed attachment should be marked processed."""

    message_id = make_test_email()

    storage.register_email_attachment(
        message_id=message_id,
        part_id="part-001",
        filename="invoice.pdf",
    )

    storage.mark_attachment_downloaded(
        message_id,
        "part-001",
        "data/email_attachments/invoice.pdf",
    )

    storage.mark_attachment_processed(
        message_id,
        "part-001",
    )

    record = storage.get_email_attachment_record(
        message_id,
        "part-001",
    )

    assert record["status"] == "processed"
    assert record["error_message"] is None


def test_mark_attachment_failed_stores_error(test_db):
    """A failed attachment should retain its error message."""

    message_id = make_test_email()

    storage.register_email_attachment(
        message_id=message_id,
        part_id="part-001",
        filename="invoice.pdf",
    )

    storage.mark_attachment_failed(
        message_id,
        "part-001",
        "AI extraction failed.",
    )

    record = storage.get_email_attachment_record(
        message_id,
        "part-001",
    )

    assert record["status"] == "failed"
    assert record["error_message"] == "AI extraction failed."


def test_mark_unknown_attachment_processed_raises_error(test_db):
    """Unknown attachments must not be marked as processed."""

    with pytest.raises(LookupError):
        storage.mark_attachment_processed(
            "unknown-email",
            "unknown-part",
        )


def test_mark_unknown_attachment_failed_raises_error(test_db):
    """Unknown attachments must not be marked as failed."""

    with pytest.raises(LookupError):
        storage.mark_attachment_failed(
            "unknown-email",
            "unknown-part",
            "Test error",
        )


def test_attachment_table_rejects_invalid_status(test_db):
    """The attachment table should enforce its status constraint."""

    message_id = make_test_email()

    with pytest.raises(sqlite3.IntegrityError):
        connection = sqlite3.connect(test_db)

        try:
            connection.execute(
                """
                INSERT INTO email_attachments (
                    message_id,
                    part_id,
                    filename,
                    status
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    message_id,
                    "part-invalid",
                    "invoice.pdf",
                    "unknown",
                ),
            )

            connection.commit()

        finally:
            connection.close()

def test_get_email_attachments_returns_all_attachments(test_db):
    """All attachments for an email should be retrievable."""

    message_id = make_test_email()

    storage.register_email_attachment(
        message_id, "part-001", "invoice_one.pdf"
    )

    storage.register_email_attachment(
        message_id, "part-002", "invoice_two.pdf"
    )

    attachments = storage.get_email_attachments(message_id)

    assert len(attachments) == 2
    assert attachments[0]["filename"] == "invoice_one.pdf"
    assert attachments[1]["filename"] == "invoice_two.pdf"


def test_should_process_new_attachment(test_db):
    """An unregistered attachment should be eligible for processing."""

    assert storage.should_process_attachment(
        "unknown-email",
        "part-001",
    ) is True


def test_should_process_pending_attachment(test_db):
    """A pending attachment should be eligible for processing."""

    message_id = make_test_email()

    storage.register_email_attachment(
        message_id, "part-001", "invoice.pdf"
    )

    assert storage.should_process_attachment(
        message_id, "part-001"
    ) is True


def test_should_process_processed_attachment(test_db):
    """A processed attachment should be skipped."""

    message_id = make_test_email()

    storage.register_email_attachment(
        message_id, "part-001", "invoice.pdf"
    )

    storage.mark_attachment_processed(
        message_id, "part-001"
    )

    assert storage.should_process_attachment(
        message_id, "part-001"
    ) is False


def test_mark_attachment_pending_clears_previous_error(test_db):
    """A failed attachment should be reset for another attempt."""

    message_id = make_test_email()

    storage.register_email_attachment(
        message_id, "part-001", "invoice.pdf"
    )

    storage.mark_attachment_failed(
        message_id,
        "part-001",
        "AI extraction failed.",
    )

    storage.mark_attachment_pending(
        message_id,
        "part-001",
    )

    record = storage.get_email_attachment_record(
        message_id, "part-001"
    )

    assert record["status"] == "pending"
    assert record["error_message"] is None


def test_mark_unknown_attachment_pending_raises_error(test_db):
    """An unknown attachment cannot be reset."""

    with pytest.raises(LookupError):
        storage.mark_attachment_pending(
            "unknown-email",
            "unknown-part",
        )

def test_save_invoice_and_draft_atomically(test_db):
    """Both records should be saved successfully."""

    invoice = make_invoice()
    draft = make_quickbooks_draft()

    invoice_id, draft_id = (
        storage.save_invoice_and_quickbooks_draft(
            invoice=invoice,
            source_file="fictional_invoice.pdf",
            draft=draft,
        )
    )

    assert invoice_id > 0
    assert draft_id > 0

    assert len(storage.get_all_invoices()) == 1
    assert len(storage.get_all_quickbooks_drafts()) == 1


def test_atomic_save_creates_airtable_sync_jobs(test_db):
    """Saving an invoice and draft should enqueue both Airtable sync jobs."""

    invoice = make_invoice()
    draft = make_quickbooks_draft()

    invoice_id, draft_id = storage.save_invoice_and_quickbooks_draft(
        invoice=invoice,
        source_file="fictional_invoice.pdf",
        draft=draft,
    )

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT entity_type, local_record_id, status
            FROM airtable_sync
            ORDER BY id ASC
        """)

        records = cursor.fetchall()

        assert records == [
            ("invoice", invoice_id, "pending"),
            ("quickbooks_draft", draft_id, "pending"),
        ]

    finally:
        connection.close()


def test_atomic_save_rolls_back_sync_jobs_if_draft_fails(test_db):
    """Failed atomic saves must not leave Airtable sync jobs behind."""

    invoice = make_invoice()
    draft = make_quickbooks_draft()

    # Insert a draft first to trigger the unique constraint.
    storage.save_quickbooks_draft(draft)

    with pytest.raises(sqlite3.IntegrityError):
        storage.save_invoice_and_quickbooks_draft(
            invoice=invoice,
            source_file="fictional_invoice.pdf",
            draft=draft,
        )

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM invoices")
        invoice_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM airtable_sync")
        sync_count = cursor.fetchone()[0]

        assert invoice_count == 0
        assert sync_count == 0

    finally:
        connection.close()

def test_atomic_save_rolls_back_invoice_if_draft_fails(test_db):
    """The invoice must be rolled back if draft insertion fails."""

    invoice = make_invoice()
    draft = make_quickbooks_draft()

    # Insert an existing draft to trigger the unique constraint.
    storage.save_quickbooks_draft(draft)

    with pytest.raises(sqlite3.IntegrityError):
        storage.save_invoice_and_quickbooks_draft(
            invoice=invoice,
            source_file="fictional_invoice.pdf",
            draft=draft,
        )

    # Neither an additional invoice nor an additional draft
    # should have been committed.
    assert storage.get_all_invoices() == []
    assert len(storage.get_all_quickbooks_drafts()) == 1

def test_email_stops_after_max_retries(test_db):
    message_id = make_test_email()

    for attempt in range(storage.MAX_RETRIES):
        storage.mark_email_failed(
            message_id,
            f"Temporary failure {attempt + 1}",
            failure_type="transient",
        )

    record = storage.get_email_processing_record(message_id)

    assert record["retry_count"] == storage.MAX_RETRIES
    assert record["status"] == "failed"
    assert storage.should_process_email(message_id) is False


def test_attachment_stops_after_max_retries(test_db):
    message_id = make_test_email()

    storage.register_email_attachment(
        message_id,
        "part-001",
        "invoice.pdf",
    )

    for attempt in range(storage.MAX_RETRIES):
        storage.mark_attachment_failed(
            message_id,
            "part-001",
            f"Temporary failure {attempt + 1}",
            failure_type="transient",
        )

    record = storage.get_email_attachment_record(
        message_id,
        "part-001",
    )

    assert record["retry_count"] == storage.MAX_RETRIES
    assert record["status"] == "failed"

    assert storage.should_process_attachment(
        message_id,
        "part-001",
    ) is False

def test_permanent_email_failure_is_not_retried(test_db):
    message_id = make_test_email()

    storage.mark_email_failed(
        message_id,
        "Invalid email data",
        failure_type="permanent",
    )

    assert storage.should_process_email(message_id) is False


def test_permanent_attachment_failure_is_not_retried(test_db):
    message_id = make_test_email()

    storage.register_email_attachment(
        message_id,
        "part-001",
        "invoice.pdf",
    )

    storage.mark_attachment_failed(
        message_id,
        "part-001",
        "Invalid PDF",
        failure_type="permanent",
    )

    assert storage.should_process_attachment(
        message_id,
        "part-001",
    ) is False

def test_manual_email_reset_preserves_retry_count(test_db):
    message_id = make_test_email()

    for attempt in range(storage.MAX_RETRIES):
        storage.mark_email_failed(
            message_id,
            f"Temporary failure {attempt + 1}",
            failure_type="transient",
        )

    storage.mark_email_pending(message_id)

    record = storage.get_email_processing_record(message_id)

    assert record["status"] == "pending"
    assert record["retry_count"] == storage.MAX_RETRIES
    assert record["failure_type"] is None
    assert record["error_message"] is None
    assert storage.should_process_email(message_id) is True


def test_manual_attachment_reset_preserves_retry_count(test_db):
    message_id = make_test_email()

    storage.register_email_attachment(
        message_id,
        "part-001",
        "invoice.pdf",
    )

    for attempt in range(storage.MAX_RETRIES):
        storage.mark_attachment_failed(
            message_id,
            "part-001",
            f"Temporary failure {attempt + 1}",
            failure_type="transient",
        )

    storage.mark_attachment_pending(message_id, "part-001")

    record = storage.get_email_attachment_record(
        message_id,
        "part-001",
    )

    assert record["status"] == "pending"
    assert record["retry_count"] == storage.MAX_RETRIES
    assert record["failure_type"] is None
    assert record["error_message"] is None

    assert storage.should_process_attachment(
        message_id,
        "part-001",
    ) is True

def test_processed_email_cannot_be_reset_to_pending(test_db):
    message_id = make_test_email()

    storage.mark_email_processed(message_id)

    with pytest.raises(ValueError):
        storage.mark_email_pending(message_id)

    record = storage.get_email_processing_record(message_id)

    assert record["status"] == "processed"
    assert storage.should_process_email(message_id) is False


def test_processed_attachment_cannot_be_reset_to_pending(test_db):
    message_id = make_test_email()

    storage.register_email_attachment(
        message_id,
        "part-001",
        "invoice.pdf",
    )

    storage.mark_attachment_processed(message_id, "part-001")

    with pytest.raises(ValueError):
        storage.mark_attachment_pending(message_id, "part-001")

    record = storage.get_email_attachment_record(
        message_id,
        "part-001",
    )

    assert record["status"] == "processed"
    assert storage.should_process_attachment(
        message_id,
        "part-001",
    ) is False


def create_test_airtable_job():
    """Create an isolated invoice sync job through the atomic save."""

    invoice_id, _ = storage.save_invoice_and_quickbooks_draft(
        invoice=make_invoice(),
        source_file="fictional_invoice.pdf",
        draft=make_quickbooks_draft(),
    )

    jobs = storage.get_pending_airtable_sync_jobs()

    return next(
        job for job in jobs
        if job["entity_type"] == "invoice"
        and job["local_record_id"] == invoice_id
    )


def test_get_pending_airtable_sync_jobs(test_db):
    """Pending jobs should be returned in queue order."""

    create_test_airtable_job()

    jobs = storage.get_pending_airtable_sync_jobs()

    assert len(jobs) == 2
    assert all(job["status"] == "pending" for job in jobs)


def test_get_airtable_sync_job_returns_correct_record(test_db):
    """A queue job should be retrievable by its ID."""

    job = create_test_airtable_job()

    retrieved = storage.get_airtable_sync_job(job["id"])

    assert retrieved is not None
    assert retrieved["id"] == job["id"]
    assert retrieved["entity_type"] == "invoice"


def test_mark_airtable_sync_synced(test_db):
    """Successful synchronization should store the Airtable record ID."""

    job = create_test_airtable_job()

    storage.mark_airtable_sync_synced(
        job["id"],
        "recTest123",
    )

    updated = storage.get_airtable_sync_job(job["id"])

    assert updated["status"] == "synced"
    assert updated["airtable_record_id"] == "recTest123"
    assert updated["error_message"] is None


def test_mark_airtable_sync_synced_is_idempotent(test_db):
    """Repeating the same successful update should be safe."""

    job = create_test_airtable_job()

    storage.mark_airtable_sync_synced(
        job["id"],
        "recTest123",
    )

    storage.mark_airtable_sync_synced(
        job["id"],
        "recTest123",
    )

    updated = storage.get_airtable_sync_job(job["id"])

    assert updated["status"] == "synced"
    assert updated["airtable_record_id"] == "recTest123"


def test_mark_airtable_sync_failed_increments_retry_count(test_db):
    """A failed synchronization should increment retry_count."""

    job = create_test_airtable_job()

    storage.mark_airtable_sync_failed(
        job["id"],
        "Temporary Airtable connection failure.",
    )

    updated = storage.get_airtable_sync_job(job["id"])

    assert updated["status"] == "failed"
    assert updated["retry_count"] == 1
    assert updated["error_message"] == (
        "Temporary Airtable connection failure."
    )


def test_mark_airtable_sync_pending_preserves_retry_count(test_db):
    """Manual recovery should preserve previous retry attempts."""

    job = create_test_airtable_job()

    storage.mark_airtable_sync_failed(
        job["id"],
        "Temporary failure.",
    )

    storage.mark_airtable_sync_pending(job["id"])

    updated = storage.get_airtable_sync_job(job["id"])

    assert updated["status"] == "pending"
    assert updated["retry_count"] == 1
    assert updated["error_message"] is None


def test_failed_jobs_are_excluded_from_pending_queue(test_db):
    """Failed jobs should not be returned as pending jobs."""

    job = create_test_airtable_job()

    storage.mark_airtable_sync_failed(
        job["id"],
        "Temporary failure.",
    )

    pending_jobs = storage.get_pending_airtable_sync_jobs()

    assert all(
        item["id"] != job["id"]
        for item in pending_jobs
    )


def test_mark_unknown_airtable_job_synced_raises_error(test_db):
    with pytest.raises(LookupError):
        storage.mark_airtable_sync_synced(
            9999,
            "recUnknown",
        )


def test_mark_unknown_airtable_job_failed_raises_error(test_db):
    with pytest.raises(LookupError):
        storage.mark_airtable_sync_failed(
            9999,
            "Temporary failure.",
        )


def test_mark_unknown_airtable_job_pending_raises_error(test_db):
    with pytest.raises(LookupError):
        storage.mark_airtable_sync_pending(9999)


def test_airtable_sync_rejects_invalid_retry_limit(test_db):
    with pytest.raises(ValueError):
        storage.get_pending_airtable_sync_jobs(limit=0)


def test_get_invoice_by_id_returns_invoice_and_source_file(test_db):
    """Retrieve an invoice and its original source path by ID."""

    invoice = make_invoice()
    source_file = "data/fictional_invoice.pdf"

    invoice_id = storage.save_invoice(invoice, source_file)

    result = storage.get_invoice_by_id(invoice_id)

    assert result is not None

    retrieved_invoice, retrieved_source = result

    assert retrieved_invoice.invoice_number == invoice.invoice_number
    assert retrieved_invoice.vendor_name == invoice.vendor_name
    assert retrieved_invoice.line_items == invoice.line_items
    assert retrieved_source == source_file


def test_get_invoice_by_id_returns_none_for_unknown_id(test_db):
    assert storage.get_invoice_by_id(9999) is None


def test_get_invoice_by_id_rejects_invalid_id(test_db):
    with pytest.raises(ValueError):
        storage.get_invoice_by_id(0)


def test_get_quickbooks_draft_by_id_returns_draft(test_db):
    """Retrieve a QuickBooks draft using its SQLite ID."""

    draft = make_quickbooks_draft()

    draft_id = storage.save_quickbooks_draft(draft)

    retrieved = storage.get_quickbooks_draft_by_id(draft_id)

    assert retrieved is not None
    assert retrieved.bill_number == draft.bill_number
    assert retrieved.vendor_name == draft.vendor_name
    assert retrieved.line_items == draft.line_items
    assert retrieved.total_amount == draft.total_amount


def test_get_quickbooks_draft_by_id_returns_none_for_unknown_id(test_db):
    assert storage.get_quickbooks_draft_by_id(9999) is None


def test_get_quickbooks_draft_by_id_rejects_invalid_id(test_db):
    with pytest.raises(ValueError):
        storage.get_quickbooks_draft_by_id(0)

def test_airtable_sync_table_has_retry_columns(test_db):
    connection = storage.get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA table_info(airtable_sync)")

        columns = {
            row[1] for row in cursor.fetchall()
        }

        assert "failure_type" in columns
        assert "next_retry_at" in columns

    finally:
        connection.close()

def test_airtable_retry_migration_preserves_existing_job(test_db):
    connection = storage.get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO airtable_sync (
                entity_type,
                local_record_id,
                status,
                retry_count,
                error_message
            )
            VALUES ('quickbooks_draft', 987654321, 'failed', 2, 'Previous failure')
        """)

        job_id = cursor.lastrowid
        connection.commit()

    finally:
        connection.close()

    storage.initialise_database()

    job = storage.get_airtable_sync_job(job_id)

    assert job is not None
    assert job["entity_type"] == "quickbooks_draft"
    assert job["local_record_id"] == 987654321
    assert job["status"] == "failed"
    assert job["retry_count"] == 2
    assert job["error_message"] == "Previous failure"
    assert job["failure_type"] is None
    assert job["next_retry_at"] is None


def test_airtable_transient_failure_schedules_first_retry(test_db):
    from datetime import datetime, timedelta, timezone

    connection = storage.get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO airtable_sync (
                entity_type,
                local_record_id,
                status
            )
            VALUES ('invoice', 987654321, 'pending')
        """)

        job_id = cursor.lastrowid
        connection.commit()

    finally:
        connection.close()

    before = datetime.now(timezone.utc)

    storage.mark_airtable_sync_failed(
        job_id,
        "Temporary API failure",
        failure_type="transient",
    )

    after = datetime.now(timezone.utc)

    job = storage.get_airtable_sync_job(job_id)

    assert job["status"] == "failed"
    assert job["retry_count"] == 1
    assert job["failure_type"] == "transient"

    retry_time = datetime.fromisoformat(job["next_retry_at"])

    assert before + timedelta(minutes=1) <= retry_time
    assert retry_time <= after + timedelta(minutes=1)

def test_airtable_second_failure_schedules_two_minutes(test_db):
    from datetime import datetime, timedelta, timezone

    connection = storage.get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO airtable_sync (
                entity_type,
                local_record_id,
                status,
                retry_count
            )
            VALUES ('invoice', 987654322, 'pending', 1)
        """)

        job_id = cursor.lastrowid
        connection.commit()

    finally:
        connection.close()

    before = datetime.now(timezone.utc)

    storage.mark_airtable_sync_failed(
        job_id,
        "Temporary API failure",
        failure_type="transient",
    )

    after = datetime.now(timezone.utc)

    job = storage.get_airtable_sync_job(job_id)

    assert job["retry_count"] == 2

    retry_time = datetime.fromisoformat(job["next_retry_at"])

    assert before + timedelta(minutes=2) <= retry_time
    assert retry_time <= after + timedelta(minutes=2)

def test_airtable_permanent_failure_has_no_retry(test_db):
    connection = storage.get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO airtable_sync (
                entity_type,
                local_record_id,
                status
            )
            VALUES ('invoice', 987654323, 'pending')
        """)

        job_id = cursor.lastrowid
        connection.commit()

    finally:
        connection.close()

    storage.mark_airtable_sync_failed(
        job_id,
        "Invalid Airtable field configuration",
        failure_type="permanent",
    )

    job = storage.get_airtable_sync_job(job_id)

    assert job["status"] == "failed"
    assert job["retry_count"] == 1
    assert job["failure_type"] == "permanent"
    assert job["next_retry_at"] is None

def test_airtable_fifth_failure_exhausts_retries(test_db):
    connection = storage.get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO airtable_sync (
                entity_type,
                local_record_id,
                status,
                retry_count
            )
            VALUES ('invoice', 987654324, 'pending', 4)
        """)

        job_id = cursor.lastrowid
        connection.commit()

    finally:
        connection.close()

    storage.mark_airtable_sync_failed(
        job_id,
        "Temporary API failure",
        failure_type="transient",
    )

    job = storage.get_airtable_sync_job(job_id)

    assert job["retry_count"] == 5
    assert job["status"] == "failed"
    assert job["next_retry_at"] is None


from datetime import datetime, timedelta, timezone


def test_promote_due_airtable_sync_retry(test_db):
    """Promote an eligible transient failure whose retry time has arrived."""
    connection = storage.get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO airtable_sync (
                entity_type, local_record_id, status,
                retry_count, error_message, failure_type,
                next_retry_at
            )
            VALUES (
                'invoice', 987654321, 'failed',
                1, 'Temporary API error', 'transient',
                ?
            )
            """,
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),),
        )
        job_id = cursor.lastrowid
        connection.commit()
    finally:
        connection.close()

    promoted = storage.promote_due_airtable_sync_retries()

    job = storage.get_airtable_sync_job(job_id)

    assert promoted == 1
    assert job["status"] == "pending"
    assert job["retry_count"] == 1
    assert job["error_message"] is None
    assert job["failure_type"] is None
    assert job["next_retry_at"] is None


def test_do_not_promote_future_airtable_sync_retry(test_db):
    """Do not promote a retry scheduled for the future."""
    connection = storage.get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO airtable_sync (
                entity_type, local_record_id, status,
                retry_count, failure_type, next_retry_at
            )
            VALUES (
                'invoice', 987654322, 'failed',
                1, 'transient', ?
            )
            """,
            ((datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),),
        )
        job_id = cursor.lastrowid
        connection.commit()
    finally:
        connection.close()

    promoted = storage.promote_due_airtable_sync_retries()

    job = storage.get_airtable_sync_job(job_id)

    assert promoted == 0
    assert job["status"] == "failed"


def test_do_not_promote_permanent_airtable_sync_failure(test_db):
    """Permanent failures must not be automatically retried."""
    connection = storage.get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO airtable_sync (
                entity_type, local_record_id, status,
                retry_count, failure_type, next_retry_at
            )
            VALUES (
                'invoice', 987654323, 'failed',
                1, 'permanent', ?
            )
            """,
            ((datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),),
        )
        job_id = cursor.lastrowid
        connection.commit()
    finally:
        connection.close()

    promoted = storage.promote_due_airtable_sync_retries()

    job = storage.get_airtable_sync_job(job_id)

    assert promoted == 0
    assert job["status"] == "failed"


def test_do_not_promote_exhausted_airtable_sync_retries(test_db):
    """Jobs that exhausted their retry allowance must remain failed."""
    connection = storage.get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO airtable_sync (
                entity_type, local_record_id, status,
                retry_count, failure_type, next_retry_at
            )
            VALUES (
                'invoice', 987654324, 'failed',
                ?, 'transient', ?
            )
            """,
            (
                storage.MAX_AIRTABLE_RETRIES,
                (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            ),
        )
        job_id = cursor.lastrowid
        connection.commit()
    finally:
        connection.close()

    promoted = storage.promote_due_airtable_sync_retries()

    job = storage.get_airtable_sync_job(job_id)

    assert promoted == 0
    assert job["status"] == "failed"


def test_promote_airtable_sync_retries_respects_limit(test_db):
    """Promotion must not exceed the requested batch limit."""
    connection = storage.get_connection()

    job_ids = []

    try:
        cursor = connection.cursor()

        for local_id in range(987654325, 987654328):
            cursor.execute(
                """
                INSERT INTO airtable_sync (
                    entity_type, local_record_id, status,
                    retry_count, failure_type, next_retry_at
                )
                VALUES (
                    'invoice', ?, 'failed',
                    1, 'transient', ?
                )
                """,
                (
                    local_id,
                    (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
                ),
            )
            job_ids.append(cursor.lastrowid)

        connection.commit()
    finally:
        connection.close()

    promoted = storage.promote_due_airtable_sync_retries(limit=2)

    assert promoted == 2

    jobs = [storage.get_airtable_sync_job(job_id) for job_id in job_ids]

    assert sum(job["status"] == "pending" for job in jobs) == 2
    assert sum(job["status"] == "failed" for job in jobs) == 1


def test_promote_airtable_sync_retries_rejects_invalid_limit(test_db):
    """Reject zero or negative promotion limits."""
    with pytest.raises(ValueError):
        storage.promote_due_airtable_sync_retries(limit=0)

    with pytest.raises(ValueError):
        storage.promote_due_airtable_sync_retries(limit=-1)
