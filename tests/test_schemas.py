from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from src.schemas import Invoice, InvoiceLineItem, InvoiceProcessingResult

def test_addition():
    assert 1 + 1 == 2


def test_valid_invoice_line_item():
    item = InvoiceLineItem(
        description="Laptop setup and configuration",
        quantity=Decimal("2"),
        unit_price=Decimal("185000.00"),
        amount=Decimal("370000.00"),
    )

    assert item.description == "Laptop setup and configuration"
    assert item.amount == Decimal("370000.00")


def test_invoice_line_item_rejects_zero_quantity():
    with pytest.raises(ValidationError):
        InvoiceLineItem(
            description="Laptop setup and configuration",
            quantity=Decimal("0"),
            unit_price=Decimal("185000.00"),
            amount=Decimal("0.00"),
        )


def test_valid_invoice():
    invoice = Invoice(
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
            InvoiceLineItem(
                description="Cloud backup configuration",
                quantity=Decimal("1"),
                unit_price=Decimal("60000.00"),
                amount=Decimal("60000.00"),
            ),
        ],
        subtotal=Decimal("525000.00"),
        tax_amount=Decimal("39375.00"),
        total_amount=Decimal("564375.00"),
    )

    assert invoice.vendor_name == "NovaTech Office Solutions"
    assert invoice.invoice_number == "INV-2026-1048"
    assert invoice.total_amount == Decimal("564375.00")


def test_invoice_rejects_missing_vendor_name():
    with pytest.raises(ValidationError):
        Invoice(
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
                )
            ],
            subtotal=Decimal("370000.00"),
            tax_amount=Decimal("27750.00"),
            total_amount=Decimal("397750.00"),
        )


def test_invoice_accepts_zero_tax():
    invoice = Invoice(
        vendor_name="NovaTech Office Solutions",
        customer_name="BrightPath Creative Studio",
        invoice_number="INV-2026-1049",
        invoice_date=date(2026, 10, 28),
        currency="NGN",
        line_items=[
            InvoiceLineItem(
                description="Laptop setup and configuration",
                quantity=Decimal("1"),
                unit_price=Decimal("185000.00"),
                amount=Decimal("185000.00"),
            )
        ],
        subtotal=Decimal("185000.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("185000.00"),
    )

    assert invoice.tax_amount == Decimal("0.00")

def test_invoice_missing_vendor_name():
    invoice_data = {
        "customer_name": "BrightPath Creative Studio",
        "invoice_number": "INV-2026-1048",
        "invoice_date": "2026-10-27",
        "due_date": "2026-11-10",
        "currency": "NGN",
        "line_items": [
            {
                "description": "Laptop setup and configuration",
                "quantity": 2,
                "unit_price": 185000,
                "amount": 370000,
            }
        ],
        "subtotal": 370000,
        "tax_amount": 27750,
        "total_amount": 397750,
    }

    with pytest.raises(ValidationError):
        Invoice.model_validate(invoice_data)


def test_successful_invoice_processing_result():
    invoice = Invoice(
        vendor_name="NovaTech Office Solutions",
        customer_name="BrightPath Creative Studio",
        invoice_number="INV-2026-1048",
        invoice_date="2026-10-27",
        due_date="2026-11-10",
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
        tax_amount=Decimal("39375.00"),
        total_amount=Decimal("564375.00"),
    )

    result = InvoiceProcessingResult(
        success=True,
        invoice=invoice,
        source_file="data/fictional_invoice.pdf",
    )

    assert result.success is True
    assert result.errors == []
    assert result.source_file == "data/fictional_invoice.pdf"
    assert isinstance(result.invoice, Invoice)


def test_failed_invoice_processing_result():
    invoice = Invoice(
        vendor_name="NovaTech Office Solutions",
        customer_name="BrightPath Creative Studio",
        invoice_number="INV-2026-1048",
        invoice_date="2026-10-27",
        due_date="2026-11-10",
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
        tax_amount=Decimal("39375.00"),
        total_amount=Decimal("564375.00"),
    )

    result = InvoiceProcessingResult(
        success=False,
        invoice=invoice,
        errors=[
            "Invoice subtotal does not match line item amounts."
        ],
        source_file="data/fictional_invoice.pdf",
    )

    assert result.success is False
    assert len(result.errors) == 1
    assert (
        result.errors[0]
        == "Invoice subtotal does not match line item amounts."
    )
    assert result.source_file == "data/fictional_invoice.pdf"
    assert isinstance(result.invoice, Invoice)
