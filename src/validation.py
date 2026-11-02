from decimal import Decimal
from src.schemas import Invoice, InvoiceLineItem

def validate_line_item_amount(
    item: InvoiceLineItem,
    tolerance: Decimal = Decimal("0.01"),
) -> bool:
    """Validate a line item's amount against quantity × unit price."""
    if tolerance < 0:
        raise ValueError("Tolerance cannot be negative.")

    expected_amount = item.quantity * item.unit_price
    difference = abs(expected_amount - item.amount)

    return difference <= tolerance


def validate_invoice_subtotal(
    invoice: Invoice,
    tolerance: Decimal = Decimal("0.01"),
) -> bool:
    """
    Validate that the invoice subtotal equals the sum
    of all line item amounts, within the permitted tolerance.
    """
    if tolerance < 0:
        raise ValueError("Tolerance cannot be negative.")

    calculated_subtotal = sum(
        (item.amount for item in invoice.line_items),
        Decimal("0"),
    )

    difference = abs(calculated_subtotal - invoice.subtotal)

    return difference <= tolerance


def validate_invoice_total(
    invoice: Invoice,
    tolerance: Decimal = Decimal("0.01"),
) -> bool:
    """
    Validate that the invoice total equals subtotal plus tax,
    within the permitted tolerance.
    """
    if tolerance < 0:
        raise ValueError("Tolerance cannot be negative.")

    tax_amount = (
        invoice.tax_amount
        if invoice.tax_amount is not None
        else Decimal("0")
    )

    expected_total = invoice.subtotal + tax_amount

    difference = abs(expected_total - invoice.total_amount)

    return difference <= tolerance

def validate_invoice_dates(invoice: Invoice) -> bool:
    """
    Validate that the invoice due date is not earlier
    than the invoice date.

    If no due date is provided, return True.
    """
    if invoice.due_date is None:
        return True

    return invoice.due_date >= invoice.invoice_date


def is_duplicate_invoice(
    invoice: Invoice,
    existing_invoices: list[Invoice],
) -> bool:
    """
    Check whether an invoice already exists.

    An invoice is considered a duplicate when both its
    vendor name and invoice number match an existing invoice.
    """
    for existing_invoice in existing_invoices:
        if (
            invoice.vendor_name == existing_invoice.vendor_name
            and invoice.invoice_number == existing_invoice.invoice_number
        ):
            return True

    return False

def validate_invoice(
    invoice: Invoice,
    existing_invoices: list[Invoice],
) -> list[str]:
    """
    Run all invoice business-rule validations.

    Returns:
        An empty list if the invoice passes all checks.
        Otherwise, a list containing all validation errors.
    """
    errors = []

    # 1. Validate individual line-item amounts
    if not all(
        validate_line_item_amount(item)
        for item in invoice.line_items
    ):
        errors.append(
            "One or more line items have incorrect amounts."
        )

    # 2. Validate invoice subtotal
    if not validate_invoice_subtotal(invoice):
        errors.append(
            "Invoice subtotal does not match line item amounts."
        )

    # 3. Validate invoice total
    if not validate_invoice_total(invoice):
        errors.append(
            "Invoice total does not match subtotal plus tax."
        )

    # 4. Validate invoice dates
    if not validate_invoice_dates(invoice):
        errors.append(
            "Due date cannot be earlier than invoice date."
        )

    # 5. Check for duplicate invoices
    if is_duplicate_invoice(invoice, existing_invoices):
        errors.append(
            "Duplicate invoice detected."
        )

    return errors