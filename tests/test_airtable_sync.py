
import json
import pytest

from src.airtable_sync import (
    decimal_to_number,
    invoice_to_airtable_fields,
    quickbooks_draft_to_airtable_fields,
)

from src.schemas import (
    Invoice,
    InvoiceLineItem,
    QuickBooksBillDraft,
    QuickBooksBillLineItem,
)

from datetime import date
from decimal import Decimal


def make_invoice():
    return Invoice(
        vendor_name="NovaTech Office Solutions",
        customer_name="BrightPath Creative Studio",
        invoice_number="INV-2026-1048",
        invoice_date=date(2026, 10, 27),
        due_date=date(2026, 11, 10),
        currency="NGN",
        line_items=[
            InvoiceLineItem(
                description="Laptop setup and configuration",
                quantity=Decimal("2"),
                unit_price=Decimal("185000.00"),
                amount=Decimal("370000.00"),
            ),
        ],
        subtotal=Decimal("370000.00"),
        tax_amount=Decimal("27750.00"),
        total_amount=Decimal("397750.00"),
    )


def make_draft():
    return QuickBooksBillDraft(
        vendor_name="NovaTech Office Solutions",
        bill_number="INV-2026-1048",
        bill_date=date(2026, 10, 27),
        due_date=date(2026, 11, 10),
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
        tax_amount=Decimal("27750.00"),
        total_amount=Decimal("397750.00"),
        status="draft",
    )


def test_decimal_to_number():
    assert decimal_to_number(Decimal("525000.00")) == 525000.0


def test_decimal_to_number_handles_none():
    assert decimal_to_number(None) is None


def test_invoice_to_airtable_fields():
    invoice = make_invoice()

    fields = invoice_to_airtable_fields(
        invoice,
        "data/incoming/invoice.pdf",
        1,
    )

    assert fields["Invoice Number"] == "INV-2026-1048"
    assert fields["Vendor Name"] == "NovaTech Office Solutions"
    assert fields["Customer Name"] == "BrightPath Creative Studio"
    assert fields["Subtotal"] == 370000.0
    assert fields["Tax Amount"] == 27750.0
    assert fields["Total Amount"] == 397750.0
    assert fields["SQLite Invoice ID"] == 1


def test_invoice_line_items_are_valid_json():
    fields = invoice_to_airtable_fields(
        make_invoice(),
        "data/incoming/invoice.pdf",
        1,
    )

    line_items = json.loads(fields["Line Items"])

    assert len(line_items) == 1
    assert line_items[0]["description"] == (
        "Laptop setup and configuration"
    )


def test_invoice_mapping_handles_optional_values():
    invoice = make_invoice().model_copy(
        update={
            "due_date": None,
            "tax_amount": None,
        }
    )

    fields = invoice_to_airtable_fields(
        invoice,
        "invoice.pdf",
        1,
    )

    assert fields["Due Date"] is None
    assert fields["Tax Amount"] is None


def test_invoice_mapping_rejects_invalid_sqlite_id():
    with pytest.raises(ValueError):
        invoice_to_airtable_fields(
            make_invoice(),
            "invoice.pdf",
            0,
        )


def test_quickbooks_draft_to_airtable_fields():
    draft = make_draft()

    fields = quickbooks_draft_to_airtable_fields(
        draft,
        5,
    )

    assert fields["Bill Number"] == "INV-2026-1048"
    assert fields["Vendor Name"] == "NovaTech Office Solutions"
    assert fields["Subtotal"] == 370000.0
    assert fields["Total Amount"] == 397750.0
    assert fields["Draft Status"] == "draft"
    assert fields["SQLite Draft ID"] == 5


def test_quickbooks_draft_line_items_are_valid_json():
    fields = quickbooks_draft_to_airtable_fields(
        make_draft(),
        5,
    )

    line_items = json.loads(fields["Line Items"])

    assert len(line_items) == 1
    assert line_items[0]["description"] == (
        "Laptop setup and configuration"
    )


def test_quickbooks_draft_mapping_rejects_invalid_sqlite_id():
    with pytest.raises(ValueError):
        quickbooks_draft_to_airtable_fields(
            make_draft(),
            0,
        )
