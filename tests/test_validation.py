from decimal import Decimal
import pytest
from src.schemas import InvoiceLineItem, Invoice
from src.validation import validate_line_item_amount, validate_invoice_subtotal, validate_invoice_total, validate_invoice_dates, is_duplicate_invoice, validate_invoice
from datetime import date

def make_line_item(amount):
    return InvoiceLineItem(
        description="Laptop setup and configuration",
        quantity=Decimal("2"),
        unit_price=Decimal("185000.00"),
        amount=Decimal(amount),
    )


def test_exact_amount():
    item = make_line_item("370000.00")

    assert validate_line_item_amount(item) is True


def test_small_rounding_difference():
    item = make_line_item("370000.01")

    assert validate_line_item_amount(item) is True


def test_amount_exceeds_tolerance():
    item = make_line_item("370000.02")

    assert validate_line_item_amount(item) is False


def test_negative_difference_within_tolerance():
    item = make_line_item("369999.99")

    assert validate_line_item_amount(item) is True


def test_custom_tolerance():
    item = make_line_item("370000.05")

    assert (
        validate_line_item_amount(
            item,
            tolerance=Decimal("0.10"),
        )
        is True
    )


def test_negative_tolerance_rejected():
    item = make_line_item("370000.00")

    with pytest.raises(ValueError):
        validate_line_item_amount(
            item,
            tolerance=Decimal("-0.01"),
        )


def make_invoice(subtotal):
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
                "quantity": 2,
                "unit_price": 185000,
                "amount": 370000,
            },
            {
                "description": "Network installation and testing",
                "quantity": 1,
                "unit_price": 95000,
                "amount": 95000,
            },
            {
                "description": "Cloud backup configuration",
                "quantity": 1,
                "unit_price": 60000,
                "amount": 60000,
            },
        ],
        subtotal=subtotal,
        tax_amount=39375,
        total_amount=564375,
    )


def test_exact_subtotal():
    invoice = make_invoice("525000.00")

    assert validate_invoice_subtotal(invoice) is True


def test_subtotal_difference_within_tolerance():
    invoice = make_invoice("525000.01")

    assert validate_invoice_subtotal(invoice) is True


def test_subtotal_difference_exceeding_tolerance():
    invoice = make_invoice("525000.02")

    assert validate_invoice_subtotal(invoice) is False


def test_custom_tolerance():
    invoice = make_invoice("525000.05")

    assert validate_invoice_subtotal(
        invoice,
        tolerance=Decimal("0.10"),
    ) is True


def test_negative_tolerance_rejected():
    invoice = make_invoice("525000.00")

    with pytest.raises(ValueError):
        validate_invoice_subtotal(
            invoice,
            tolerance=Decimal("-0.01"),
        )


def test_correct_invoice_total():
    invoice = make_invoice("525000.00")

    assert validate_invoice_total(invoice) is True


def test_total_difference_within_tolerance():
    invoice = make_invoice("525000.00")
    invoice.total_amount = Decimal("564375.01")

    assert validate_invoice_total(invoice) is True


def test_total_difference_exceeding_tolerance():
    invoice = make_invoice("525000.00")
    invoice.total_amount = Decimal("564375.02")

    assert validate_invoice_total(invoice) is False


def test_missing_tax_amount():
    invoice = make_invoice("525000.00")
    invoice.tax_amount = None
    invoice.total_amount = Decimal("525000.00")

    assert validate_invoice_total(invoice) is True


def test_custom_tolerance():
    invoice = make_invoice("525000.00")
    invoice.total_amount = Decimal("564375.05")

    assert validate_invoice_total(
        invoice,
        tolerance=Decimal("0.10"),
    ) is True


def test_negative_tolerance_rejected():
    invoice = make_invoice("525000.00")

    with pytest.raises(ValueError):
        validate_invoice_total(
            invoice,
            tolerance=Decimal("-0.01"),
        )


def test_due_date_later_than_invoice_date():
    invoice = make_invoice("525000.00")

    invoice.due_date = date(2026, 11, 10)

    assert validate_invoice_dates(invoice) is True


def test_due_date_equal_to_invoice_date():
    invoice = make_invoice("525000.00")

    invoice.due_date = invoice.invoice_date

    assert validate_invoice_dates(invoice) is True


def test_due_date_earlier_than_invoice_date():
    invoice = make_invoice("525000.00")

    invoice.due_date = date(2026, 10, 20)

    assert validate_invoice_dates(invoice) is False


def test_missing_due_date():
    invoice = make_invoice("525000.00")

    invoice.due_date = None

    assert validate_invoice_dates(invoice) is True


def test_duplicate_same_vendor_and_invoice_number():
    incoming_invoice = make_invoice("525000.00")
    existing_invoice = make_invoice("525000.00")

    assert is_duplicate_invoice(
        incoming_invoice,
        [existing_invoice],
    ) is True


def test_same_vendor_different_invoice_number():
    incoming_invoice = make_invoice("525000.00")
    existing_invoice = make_invoice("525000.00")

    existing_invoice.invoice_number = "INV-2026-2000"

    assert is_duplicate_invoice(
        incoming_invoice,
        [existing_invoice],
    ) is False


def test_different_vendor_same_invoice_number():
    incoming_invoice = make_invoice("525000.00")
    existing_invoice = make_invoice("525000.00")

    existing_invoice.vendor_name = "Another Vendor Ltd"

    assert is_duplicate_invoice(
        incoming_invoice,
        [existing_invoice],
    ) is False


def test_empty_existing_invoices():
    incoming_invoice = make_invoice("525000.00")

    assert is_duplicate_invoice(
        incoming_invoice,
        [],
    ) is False


def test_valid_invoice_returns_empty_errors():
    invoice = make_invoice("525000.00")

    errors = validate_invoice(invoice, [])

    assert errors == []


def test_incorrect_line_item_amount():
    invoice = make_invoice("525000.00")

    invoice.line_items[0].amount = Decimal("369000.00")

    errors = validate_invoice(invoice, [])

    assert "One or more line items have incorrect amounts." in errors


def test_incorrect_invoice_subtotal():
    invoice = make_invoice("525000.00")

    invoice.subtotal = Decimal("530000.00")

    errors = validate_invoice(invoice, [])

    assert "Invoice subtotal does not match line item amounts." in errors


def test_incorrect_invoice_total():
    invoice = make_invoice("525000.00")

    invoice.total_amount = Decimal("570000.00")

    errors = validate_invoice(invoice, [])

    assert "Invoice total does not match subtotal plus tax." in errors


def test_invalid_invoice_due_date():
    invoice = make_invoice("525000.00")

    invoice.due_date = date(2026, 10, 20)

    errors = validate_invoice(invoice, [])

    assert "Due date cannot be earlier than invoice date." in errors


def test_duplicate_invoice():
    invoice = make_invoice("525000.00")
    existing_invoice = make_invoice("525000.00")

    errors = validate_invoice(invoice, [existing_invoice])

    assert "Duplicate invoice detected." in errors


def test_multiple_validation_errors():
    invoice = make_invoice("525000.00")

    # Introduce three independent problems.
    invoice.line_items[0].amount = Decimal("369000.00")
    invoice.total_amount = Decimal("570000.00")
    invoice.due_date = date(2026, 10, 20)

    errors = validate_invoice(invoice, [])

    assert len(errors) == 4

    assert "One or more line items have incorrect amounts." in errors
    assert "Invoice subtotal does not match line item amounts." in errors
    assert "Invoice total does not match subtotal plus tax." in errors
    assert "Due date cannot be earlier than invoice date." in errors
