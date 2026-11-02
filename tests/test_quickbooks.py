from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.schemas import (
    QuickBooksBillDraft,
    QuickBooksBillLineItem,
)
from src.quickbooks import create_bill_draft
from src.schemas import Invoice, InvoiceLineItem

def make_valid_line_item():
    """Create a valid QuickBooks bill line item."""

    return QuickBooksBillLineItem(
        description="Laptop setup and configuration",
        quantity=Decimal("2"),
        unit_price=Decimal("185000.00"),
        amount=Decimal("370000.00"),
    )


def make_valid_bill_draft():
    """Create a valid QuickBooks bill draft."""

    return QuickBooksBillDraft(
        vendor_name="NovaTech Office Solutions",
        bill_number="INV-2026-1048",
        bill_date=date(2026, 10, 27),
        due_date=date(2026, 11, 10),
        currency="NGN",
        line_items=[
            make_valid_line_item(),
        ],
        subtotal=Decimal("370000.00"),
        tax_amount=Decimal("27750.00"),
        total_amount=Decimal("397750.00"),
    )


# --------------------------------------------------
# QuickBooksBillLineItem tests
# --------------------------------------------------


def test_valid_quickbooks_line_item():
    """A valid line item should be created successfully."""

    item = make_valid_line_item()

    assert isinstance(item, QuickBooksBillLineItem)
    assert item.description == "Laptop setup and configuration"
    assert item.quantity == Decimal("2")
    assert item.unit_price == Decimal("185000.00")
    assert item.amount == Decimal("370000.00")


def test_quickbooks_line_item_rejects_zero_quantity():
    """Quantity must be greater than zero."""

    with pytest.raises(ValidationError):
        QuickBooksBillLineItem(
            description="Laptop setup and configuration",
            quantity=Decimal("0"),
            unit_price=Decimal("185000.00"),
            amount=Decimal("0.00"),
        )


def test_quickbooks_line_item_rejects_negative_unit_price():
    """Unit price cannot be negative."""

    with pytest.raises(ValidationError):
        QuickBooksBillLineItem(
            description="Laptop setup and configuration",
            quantity=Decimal("2"),
            unit_price=Decimal("-185000.00"),
            amount=Decimal("370000.00"),
        )


# --------------------------------------------------
# QuickBooksBillDraft tests
# --------------------------------------------------


def test_valid_quickbooks_bill_draft():
    """A valid bill draft should be created successfully."""

    draft = make_valid_bill_draft()

    assert isinstance(draft, QuickBooksBillDraft)
    assert draft.vendor_name == "NovaTech Office Solutions"
    assert draft.bill_number == "INV-2026-1048"
    assert draft.bill_date == date(2026, 10, 27)
    assert draft.currency == "NGN"
    assert len(draft.line_items) == 1
    assert draft.total_amount == Decimal("397750.00")


def test_quickbooks_bill_draft_rejects_missing_vendor_name():
    """Vendor name is required."""

    with pytest.raises(ValidationError):
        QuickBooksBillDraft(
            bill_number="INV-2026-1048",
            bill_date=date(2026, 10, 27),
            currency="NGN",
            line_items=[make_valid_line_item()],
            subtotal=Decimal("370000.00"),
            total_amount=Decimal("370000.00"),
        )


def test_quickbooks_bill_draft_rejects_empty_line_items():
    """A bill draft must contain at least one line item."""

    with pytest.raises(ValidationError):
        QuickBooksBillDraft(
            vendor_name="NovaTech Office Solutions",
            bill_number="INV-2026-1048",
            bill_date=date(2026, 10, 27),
            currency="NGN",
            line_items=[],
            subtotal=Decimal("0.00"),
            total_amount=Decimal("0.00"),
        )


def test_quickbooks_bill_draft_rejects_negative_total_amount():
    """Total amount cannot be negative."""

    with pytest.raises(ValidationError):
        QuickBooksBillDraft(
            vendor_name="NovaTech Office Solutions",
            bill_number="INV-2026-1048",
            bill_date=date(2026, 10, 27),
            currency="NGN",
            line_items=[make_valid_line_item()],
            subtotal=Decimal("370000.00"),
            total_amount=Decimal("-397750.00"),
        )


def test_quickbooks_bill_draft_defaults_to_draft_status():
    """Status should default to draft."""

    draft = make_valid_bill_draft()

    assert draft.status == "draft"


def test_quickbooks_bill_draft_rejects_invalid_status():
    """Only the permitted draft status should be accepted."""

    with pytest.raises(ValidationError):
        QuickBooksBillDraft(
            vendor_name="NovaTech Office Solutions",
            bill_number="INV-2026-1048",
            bill_date=date(2026, 10, 27),
            currency="NGN",
            line_items=[make_valid_line_item()],
            subtotal=Decimal("370000.00"),
            total_amount=Decimal("397750.00"),
            status="approved",
        )


def make_valid_invoice():
    """Create a valid source invoice for transformation tests."""

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
            InvoiceLineItem(
                description="Network installation",
                quantity=Decimal("1"),
                unit_price=Decimal("95000.00"),
                amount=Decimal("95000.00"),
            ),
        ],
        subtotal=Decimal("465000.00"),
        tax_amount=Decimal("34875.00"),
        total_amount=Decimal("499875.00"),
    )


def test_create_bill_draft_returns_correct_model():
    """Transformation should return a QuickBooksBillDraft."""

    invoice = make_valid_invoice()

    draft = create_bill_draft(invoice)

    assert isinstance(draft, QuickBooksBillDraft)


def test_create_bill_draft_maps_invoice_fields():
    """Original invoice fields should map correctly."""

    invoice = make_valid_invoice()

    draft = create_bill_draft(invoice)

    assert draft.vendor_name == invoice.vendor_name
    assert draft.bill_number == invoice.invoice_number
    assert draft.bill_date == invoice.invoice_date
    assert draft.due_date == invoice.due_date
    assert draft.currency == invoice.currency
    assert draft.subtotal == invoice.subtotal
    assert draft.tax_amount == invoice.tax_amount
    assert draft.total_amount == invoice.total_amount


def test_create_bill_draft_transforms_line_items():
    """Invoice line items should become QuickBooks bill line items."""

    invoice = make_valid_invoice()

    draft = create_bill_draft(invoice)

    assert len(draft.line_items) == len(invoice.line_items)

    for original, transformed in zip(
        invoice.line_items,
        draft.line_items,
    ):
        assert isinstance(transformed, QuickBooksBillLineItem)
        assert transformed.description == original.description
        assert transformed.quantity == original.quantity
        assert transformed.unit_price == original.unit_price
        assert transformed.amount == original.amount


def test_create_bill_draft_preserves_decimal_precision():
    """Monetary values should retain their original Decimal precision."""

    invoice = make_valid_invoice()

    draft = create_bill_draft(invoice)

    assert draft.subtotal == Decimal("465000.00")
    assert draft.tax_amount == Decimal("34875.00")
    assert draft.total_amount == Decimal("499875.00")


def test_create_bill_draft_defaults_to_draft_status():
    """The transformed bill should have draft status."""

    invoice = make_valid_invoice()

    draft = create_bill_draft(invoice)

    assert draft.status == "draft"


def test_create_bill_draft_preserves_missing_optional_values():
    """Missing due date and tax amount should remain None."""

    invoice = make_valid_invoice().model_copy(
        update={
            "due_date": None,
            "tax_amount": None,
        }
    )

    draft = create_bill_draft(invoice)

    assert draft.due_date is None
    assert draft.tax_amount is None
