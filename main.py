import argparse
import logging
from pathlib import Path

from src.logging_config import configure_logging, LOGGER_NAME
from src.pipeline import process_invoice, process_recent_invoice_emails
from src.storage import (
    initialise_database,
    get_all_invoices,
    get_all_quickbooks_drafts,
)

logger = logging.getLogger(LOGGER_NAME)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Invoice Processing Automation"
    )

    parser.add_argument(
        "--pdf",
        type=Path,
        help="Process a single invoice PDF instead of retrieving emails.",
    )

    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Email pagination offset (default: 0).",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of recent emails to process (default: 50).",
    )

    args = parser.parse_args()

    if args.start < 0:
        parser.error("--start cannot be negative.")

    if args.limit <= 0:
        parser.error("--limit must be greater than zero.")

    return args


def process_single_pdf(pdf_path):
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Invoice PDF not found: {pdf_path}")

    result = process_invoice(pdf_path)

    if result.invoice is None:
        print("\nInvoice extraction did not produce an invoice.")
        return

    invoice = result.invoice

    print("\n" + "=" * 60)
    print("INVOICE PROCESSING RESULT")
    print("=" * 60)

    print(f"Vendor: {invoice.vendor_name}")
    print(f"Customer: {invoice.customer_name}")
    print(f"Invoice Number: {invoice.invoice_number}")
    print(f"Invoice Date: {invoice.invoice_date}")
    print(f"Due Date: {invoice.due_date}")
    print(f"Currency: {invoice.currency}")

    print("\nLine Items:")
    for item in invoice.line_items:
        print(
            f"- {item.description}: "
            f"{item.quantity} x {item.unit_price}"
        )

    print("\nFinancial Summary:")
    print(f"Subtotal: {invoice.subtotal}")
    print(f"Tax: {invoice.tax_amount}")
    print(f"Total: {invoice.total_amount}")

    if result.success:
        print("\nInvoice successfully processed.")

        matching_draft = next(
            (
                draft
                for draft in get_all_quickbooks_drafts()
                if draft.get("bill_number") == invoice.invoice_number
                and draft.get("vendor_name") == invoice.vendor_name
            ),
            None,
        )

        if matching_draft:
            print("QuickBooks draft created successfully.")
            print(f"Draft Status: {matching_draft.get('status')}")
        else:
            print("No matching QuickBooks draft was found.")
    else:
        print("\nInvoice processing completed with validation errors.")

        for error in result.errors:
            print(f"- {error}")


def process_email_invoices(start, limit):
    results = process_recent_invoice_emails(
        start=start,
        limit=limit,
    )

    print("\n" + "=" * 60)
    print("EMAIL INVOICE PROCESSING SUMMARY")
    print("=" * 60)

    if not results:
        print("No invoice emails were found.")
        return

    processed = 0
    failed = 0
    skipped = 0

    for result in results:
        status = result.get("status")

        if status == "processed":
            processed += 1
        elif status == "failed":
            failed += 1
        else:
            skipped += 1

        print(f"\nSubject: {result.get('subject', 'Unknown')}")
        print(f"Status: {status}")
        print(f"Processed attachments: {len(result.get('processed_files', []))}")
        print(f"Skipped attachments: {len(result.get('skipped_files', []))}")
        print(f"Errors: {len(result.get('errors', []))}")

    print("\n" + "-" * 60)
    print(f"Emails processed successfully: {processed}")
    print(f"Emails failed: {failed}")
    print(f"Emails skipped/other: {skipped}")
    print(f"Total emails handled: {len(results)}")


def main():
    args = parse_arguments()

    configure_logging()
    logger.info("Invoice processing application started")

    try:
        initialise_database()

        if args.pdf:
            process_single_pdf(args.pdf)
        else:
            process_email_invoices(
                start=args.start,
                limit=args.limit,
            )

        print("\nDatabase Summary:")
        print(f"Total invoices: {len(get_all_invoices())}")
        print(
            "Total QuickBooks drafts: "
            f"{len(get_all_quickbooks_drafts())}"
        )

        logger.info("Invoice processing application completed")

    except Exception as error:
        logger.error(
            "Invoice processing application terminated (%s)",
            type(error).__name__,
        )
        raise


if __name__ == "__main__":
    main()
