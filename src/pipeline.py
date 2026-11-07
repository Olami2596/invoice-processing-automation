
"""
Invoice processing pipeline.

Orchestrates PDF extraction, AI invoice extraction,
business validation, atomic persistence, and email processing.
"""

import logging
import sqlite3
from pathlib import Path
from urllib.error import HTTPError, URLError

from src import storage
from src.email_ingestion import ingest_recent_invoice_emails
from src.invoice_extractor import extract_invoice_data
from src.logging_config import LOGGER_NAME
from src.pdf_extractor import extract_text_from_pdf
from src.quickbooks import create_bill_draft
from src.schemas import InvoiceProcessingResult
from src.storage import (
    get_all_invoices,
    save_invoice,
    save_quickbooks_draft,
)
from src.validation import validate_invoice


logger = logging.getLogger(LOGGER_NAME)


def classify_failure(error: Exception) -> str:
    """
    Classify an exception as transient or permanent.

    Transient failures may be retried, subject to MAX_RETRIES.
    Permanent failures are not retried automatically.
    """

    # Check HTTPError before URLError because HTTPError
    # is a subclass of URLError.
    if isinstance(error, HTTPError):
        if error.code in (408, 425, 429) or error.code >= 500:
            return "transient"
        return "permanent"

    if isinstance(error, (FileNotFoundError, PermissionError)):
        return "permanent"

    if isinstance(error, sqlite3.IntegrityError):
        return "permanent"

    if isinstance(error, sqlite3.OperationalError):
        # Database locking and temporary operational failures
        # can be retried. Other operational errors are also
        # temporarily classified as transient for now.
        return "transient"

    if isinstance(error, (TimeoutError, ConnectionError, URLError)):
        return "transient"

    # Recognise common malformed-PDF exceptions without
    # requiring a specific PDF library exception import.
    if type(error).__name__ in {
        "PDFSyntaxError",
        "PDFEncryptionError",
    }:
        return "permanent"

    # Unknown failures receive a limited retry opportunity.
    return "transient"


def classify_email_failure(attachment_records: list[dict]) -> str:
    """
    Determine the email failure type from its attachment outcomes.

    An email is transiently failed if at least one unfinished
    attachment is still eligible for retry.
    """

    for record in attachment_records:
        if record["status"] == "processed":
            continue

        if record["status"] in {"pending", "downloaded"}:
            return "transient"

        if record["status"] == "failed":
            if (
                record.get("failure_type") == "transient"
                and record.get("retry_count", 0) < storage.MAX_RETRIES
            ):
                return "transient"

    return "permanent"


def process_invoice(pdf_path, existing_invoices=None):
    """
    Process an invoice PDF from text extraction through
    AI extraction and business validation.

    Args:
        pdf_path: Path to the invoice PDF.
        existing_invoices: Previously processed invoices.

    Returns:
        An InvoiceProcessingResult containing the extracted
        invoice, validation status, errors, and source file.

    Extraction and database exceptions are allowed to propagate
    so the email-processing layer can classify and record them.
    """

    logger.info("Invoice processing started")

    # 1. Extract text from the PDF.
    invoice_text = extract_text_from_pdf(pdf_path)
    logger.info("PDF text extraction completed")

    # 2. Extract structured invoice data using AI.
    invoice = extract_invoice_data(invoice_text)
    logger.info("AI invoice extraction completed")

    # 3. Retrieve existing invoices if none were supplied.
    if existing_invoices is None:
        existing_invoices = get_all_invoices()

    # 4. Validate the extracted invoice.
    errors = validate_invoice(invoice, existing_invoices)

    if errors:
        logger.warning(
            "Invoice validation failed: %d validation issue(s)",
            len(errors),
        )
    else:
        logger.info("Invoice validation passed")

    # 5. Save valid invoices and their QuickBooks drafts atomically.
    if not errors:
        bill_draft = create_bill_draft(invoice)

        storage.save_invoice_and_quickbooks_draft(
            invoice=invoice,
            source_file=pdf_path,
            draft=bill_draft,
        )

        logger.info(
            "Invoice and QuickBooks draft saved successfully"
        )

    # 6. Return the processing result.
    return InvoiceProcessingResult(
        success=len(errors) == 0,
        invoice=invoice,
        errors=errors,
        source_file=str(pdf_path),
    )


def process_recent_invoice_emails(
    start=0,
    limit=50,
    output_directory="data/email_attachments",
):
    """
    Retrieve recent emails and process their PDF invoice attachments.

    Each attachment is tracked independently in SQLite.

    Successfully processed attachments are skipped during retries.
    Failed attachments remain eligible according to their failure
    classification and retry count.

    An email is marked processed only when all its attachments
    have been processed successfully.
    """

    # 1. Retrieve recent emails and download their PDF attachments.
    ingestion_results = ingest_recent_invoice_emails(
        start=start,
        limit=limit,
        output_directory=output_directory,
    )

    logger.info(
        "Email ingestion completed: %d email(s) retrieved",
        len(ingestion_results),
    )

    processing_results = []

    # 2. Process each email returned by the ingestion function.
    for email in ingestion_results:
        message_id = email["message_id"]
        subject = email["subject"]
        downloaded_files = email["downloaded_files"]

        logger.info("Processing email and its attachments")

        processed_files = []
        skipped_files = []
        errors = []

        try:
            # 3. Retrieve attachment tracking records.
            attachment_records = storage.get_email_attachments(
                message_id
            )

            # Map each saved PDF path to its attachment record.
            records_by_path = {
                str(Path(record["file_path"])): record
                for record in attachment_records
                if record["file_path"]
            }

            # 4. Process each downloaded PDF independently.
            for pdf_path in downloaded_files:
                pdf_path = Path(pdf_path)
                path_key = str(pdf_path)

                attachment = records_by_path.get(path_key)

                if attachment is None:
                    error_message = (
                        "No tracking record found for attachment"
                    )

                    logger.warning(
                        "Attachment has no tracking record"
                    )

                    errors.append(error_message)
                    continue

                part_id = attachment["part_id"]

                # 5. Skip successfully processed attachments,
                # permanent failures, and exhausted retries.
                if not storage.should_process_attachment(
                    message_id,
                    part_id,
                ):
                    skipped_files.append(str(pdf_path))

                    logger.info(
                        "Attachment skipped: already processed "
                        "or retry limit reached"
                    )

                    continue

                try:
                    # 6. Process the invoice.
                    result = process_invoice(pdf_path)

                    if not result.success:
                        error_message = (
                            "Invoice validation failed for attachment"
                        )

                        # Business validation failures are permanent.
                        storage.mark_attachment_failed(
                            message_id,
                            part_id,
                            error_message,
                            failure_type="permanent",
                        )

                        logger.warning(
                            "Attachment rejected: invoice validation failed"
                        )

                        errors.append(error_message)
                        continue

                    # 7. Mark successful attachment as processed.
                    storage.mark_attachment_processed(
                        message_id,
                        part_id,
                    )

                    processed_files.append(str(pdf_path))

                    logger.info(
                        "Attachment processed successfully"
                    )

                except Exception as error:
                    # Classify unexpected processing failures.
                    failure_type = classify_failure(error)

                    # Preserve the original error message for processing results
                    # and database tracking.
                    error_message = str(error)

                    storage.mark_attachment_failed(
                        message_id,
                        part_id,
                        error_message,
                        failure_type=failure_type,
                    )

                    # Keep application logs free from potentially sensitive
                    # exception messages.
                    logger.error(
                        "Attachment processing failed (%s): %s",
                        failure_type,
                        type(error).__name__,
                    )

                    errors.append(error_message)

            # 8. Re-read attachment records after processing.
            updated_records = storage.get_email_attachments(
                message_id
            )

            all_attachments_processed = (
                bool(updated_records)
                and all(
                    record["status"] == "processed"
                    for record in updated_records
                )
            )

            # 9. Update overall email status.
            if all_attachments_processed:
                storage.mark_email_processed(message_id)
                status = "processed"

                logger.info(
                    "Email processing completed successfully"
                )

            else:
                if not errors:
                    errors.append(
                        "One or more email attachments "
                        "remain unprocessed."
                    )

                failure_type = classify_email_failure(updated_records)

                storage.mark_email_failed(
                    message_id,
                    "; ".join(errors),
                    failure_type=failure_type,
                )

                status = "failed"

                logger.warning(
                    "Email processing incomplete: %d error(s)",
                    len(errors),
                )

        except Exception as error:
            # Handle unexpected email-level errors.
            failure_type = classify_failure(error)

            errors.append("Email processing failed")

            storage.mark_email_failed(
                message_id,
                "Email processing failed",
                failure_type=failure_type,
            )

            status = "failed"

            logger.error(
                "Email processing failed (%s): %s",
                failure_type,
                type(error).__name__,
            )

        # 10. Record the outcome for this email.
        processing_results.append({
            "message_id": message_id,
            "subject": subject,
            "status": status,
            "processed_files": processed_files,
            "skipped_files": skipped_files,
            "errors": errors,
        })

    return processing_results
