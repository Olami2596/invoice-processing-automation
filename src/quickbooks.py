
"""
QuickBooks bill draft transformation.

Converts validated Invoice objects into our simplified
QuickBooks-style bill draft representation.
"""

from src.schemas import (
    Invoice,
    QuickBooksBillDraft,
    QuickBooksBillLineItem,
)


def create_bill_draft(invoice: Invoice) -> QuickBooksBillDraft:
    """
    Convert a validated Invoice into a QuickBooks bill draft.

    Args:
        invoice: Validated Invoice object.

    Returns:
        A QuickBooksBillDraft containing the mapped invoice data.
    """

    # Convert invoice line items into QuickBooks bill line items.
    line_items = [
        QuickBooksBillLineItem(
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            amount=item.amount,
        )
        for item in invoice.line_items
    ]

    # Create the QuickBooks bill draft.
    bill_draft = QuickBooksBillDraft(
        vendor_name=invoice.vendor_name,
        bill_number=invoice.invoice_number,
        bill_date=invoice.invoice_date,
        due_date=invoice.due_date,
        currency=invoice.currency,
        line_items=line_items,
        subtotal=invoice.subtotal,
        tax_amount=invoice.tax_amount,
        total_amount=invoice.total_amount,
    )

    return bill_draft
