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


def test_initialise_database_creates_both_tables(test_db):
    """Database initialisation should create both application tables."""

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

    finally:
        connection.close()
