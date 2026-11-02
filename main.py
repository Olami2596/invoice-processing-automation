
from pathlib import Path
from decimal import Decimal

from src.pipeline import process_invoice
from src.storage import (
    initialise_database,
    get_all_invoices,
    get_all_quickbooks_drafts,
)


PDF_PATH = Path("data/new_fictional_invoice.pdf")


def main():
    initialise_database()

    print("=" * 60)
    print("INVOICE PROCESSING AUTOMATION")
    print("=" * 60)

    if not PDF_PATH.exists():
        raise FileNotFoundError(f"Invoice PDF not found: {PDF_PATH}")

    result = process_invoice(PDF_PATH)
    invoice = result.invoice

    print("\nEXTRACTED INVOICE DETAILS")
    print("-" * 60)

    print(f"Vendor: {invoice.vendor_name}")
    print(f"Customer: {invoice.customer_name}")
    print(f"Invoice number: {invoice.invoice_number}")
    print(f"Invoice date: {invoice.invoice_date}")
    print(f"Due date: {invoice.due_date}")
    print(f"Currency: {invoice.currency}")

    print("\nLINE ITEMS")

    for item in invoice.line_items:
        expected_amount = item.quantity * item.unit_price

        print(f"\nDescription: {item.description}")
        print(f"Quantity: {item.quantity}")
        print(f"Unit price: {item.unit_price}")
        print(f"Extracted amount: {item.amount}")
        print(f"Expected amount: {expected_amount}")

    calculated_subtotal = sum(
        (item.amount for item in invoice.line_items),
        Decimal("0"),
    )

    print("\nFINANCIAL SUMMARY")
    print("-" * 60)
    print(f"Extracted subtotal: {invoice.subtotal}")
    print(f"Calculated subtotal: {calculated_subtotal}")
    print(f"Tax: {invoice.tax_amount}")
    print(f"Total: {invoice.total_amount}")

    if result.success:
        print("\nInvoice processed successfully!")

        drafts = get_all_quickbooks_drafts()

        matching_drafts = [
            draft for draft in drafts
            if draft.vendor_name == invoice.vendor_name
            and draft.bill_number == invoice.invoice_number
        ]

        if matching_drafts:
            draft = matching_drafts[0]

            print("\nQUICKBOOKS BILL DRAFT")
            print("-" * 60)
            print(f"Vendor: {draft.vendor_name}")
            print(f"Bill number: {draft.bill_number}")
            print(f"Bill date: {draft.bill_date}")
            print(f"Subtotal: {draft.subtotal}")
            print(f"Tax: {draft.tax_amount}")
            print(f"Total: {draft.total_amount}")
            print(f"Status: {draft.status}")
        else:
            print("\nWARNING: No corresponding QuickBooks draft found.")

    else:
        print("\nInvoice processing failed.")

        for error in result.errors:
            print(f"- {error}")

    print("\nDATABASE SUMMARY")
    print("-" * 60)
    print(f"Stored invoices: {len(get_all_invoices())}")
    print(f"Stored QuickBooks drafts: {len(get_all_quickbooks_drafts())}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
