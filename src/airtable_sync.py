
import json
import logging
import os
from decimal import Decimal

from dotenv import load_dotenv

from src.logging_config import LOGGER_NAME
from src.schemas import Invoice, QuickBooksBillDraft


logger = logging.getLogger(LOGGER_NAME)


class AirtableSyncConfigurationError(Exception):
    """Raised when required Airtable sync configuration is missing."""


class AirtableDuplicateRecordError(Exception):
    """Raised when multiple Airtable records match one local SQLite ID."""


def get_airtable_table_config() -> dict[str, str]:
    """
    Load and validate Airtable table names from environment variables.
    """

    load_dotenv()

    invoices_table = os.getenv("AIRTABLE_INVOICES_TABLE", "").strip()
    drafts_table = os.getenv("AIRTABLE_DRAFTS_TABLE", "").strip()

    missing = []

    if not invoices_table:
        missing.append("AIRTABLE_INVOICES_TABLE")

    if not drafts_table:
        missing.append("AIRTABLE_DRAFTS_TABLE")

    if missing:
        raise AirtableSyncConfigurationError(
            "Missing Airtable table configuration: "
            + ", ".join(missing)
        )

    return {
        "invoices": invoices_table,
        "drafts": drafts_table,
    }


def decimal_to_number(value: Decimal | None) -> float | None:
    """
    Convert Decimal values into JSON-compatible numbers.

    Airtable number fields expect numeric values rather than
    Python Decimal objects.
    """

    if value is None:
        return None

    return float(value)


def invoice_to_airtable_fields(
    invoice: Invoice,
    source_file: str,
    sqlite_invoice_id: int,
) -> dict:
    """Transform a validated Invoice into Airtable fields."""

    if sqlite_invoice_id <= 0:
        raise ValueError("sqlite_invoice_id must be positive.")

    fields = {
        "Invoice Number": invoice.invoice_number,
        "Vendor Name": invoice.vendor_name,
        "Customer Name": invoice.customer_name,
        "Invoice Date": invoice.invoice_date.isoformat(),
        "Due Date": (
            invoice.due_date.isoformat()
            if invoice.due_date is not None
            else None
        ),
        "Currency": invoice.currency,
        "Subtotal": decimal_to_number(invoice.subtotal),
        "Tax Amount": decimal_to_number(invoice.tax_amount),
        "Total Amount": decimal_to_number(invoice.total_amount),
        "Line Items": json.dumps(
            [
                item.model_dump(mode="json")
                for item in invoice.line_items
            ]
        ),
        "Source File": str(source_file),
        "SQLite Invoice ID": sqlite_invoice_id,
    }

    logger.debug("Invoice data transformed for Airtable.")

    return fields


def quickbooks_draft_to_airtable_fields(
    draft: QuickBooksBillDraft,
    sqlite_draft_id: int,
) -> dict:
    """Transform a QuickBooksBillDraft into Airtable fields."""

    if sqlite_draft_id <= 0:
        raise ValueError("sqlite_draft_id must be positive.")

    fields = {
        "Bill Number": draft.bill_number,
        "Vendor Name": draft.vendor_name,
        "Bill Date": draft.bill_date.isoformat(),
        "Due Date": (
            draft.due_date.isoformat()
            if draft.due_date is not None
            else None
        ),
        "Currency": draft.currency,
        "Subtotal": decimal_to_number(draft.subtotal),
        "Tax Amount": decimal_to_number(draft.tax_amount),
        "Total Amount": decimal_to_number(draft.total_amount),
        "Line Items": json.dumps(
            [
                item.model_dump(mode="json")
                for item in draft.line_items
            ]
        ),
        "Draft Status": draft.status,
        "SQLite Draft ID": sqlite_draft_id,
    }

    logger.debug("QuickBooks draft data transformed for Airtable.")

    return fields


def upsert_record_by_sqlite_id(
    client,
    table_name: str,
    sqlite_id_field: str,
    sqlite_id: int,
    fields: dict,
) -> dict:
    """
    Create or update an Airtable record using its local SQLite ID.

    If one matching record exists, update it.
    If no matching record exists, create it.
    If multiple records match, stop to avoid updating the wrong record.
    """

    if sqlite_id <= 0:
        raise ValueError("SQLite ID must be a positive integer.")

    if not isinstance(table_name, str) or not table_name.strip():
        raise ValueError("Airtable table name cannot be empty.")

    if not isinstance(sqlite_id_field, str) or not sqlite_id_field.strip():
        raise ValueError("SQLite ID field cannot be empty.")

    formula = f"{{{sqlite_id_field}}}={sqlite_id}"

    records = client.list_records(
        table_name=table_name,
        page_size=100,
        max_records=2,
        filter_by_formula=formula,
    )

    if len(records) > 1:
        logger.error(
            "Multiple Airtable records found for one SQLite ID. "
            "Table: %s",
            table_name,
        )
        raise AirtableDuplicateRecordError(
            f"Multiple Airtable records match SQLite ID {sqlite_id}."
        )

    if len(records) == 1:
        record_id = records[0]["id"]

        updated_record = client.update_record(
            table_name=table_name,
            record_id=record_id,
            fields=fields,
        )

        logger.info("Existing Airtable record updated.")
        return updated_record

    created_record = client.create_record(
        table_name=table_name,
        fields=fields,
    )

    logger.info("New Airtable record created.")
    return created_record


def sync_invoice_to_airtable(
    client,
    invoice: Invoice,
    source_file: str,
    sqlite_invoice_id: int,
) -> dict:
    """Create or update an invoice in the configured Airtable table."""

    table_config = get_airtable_table_config()

    fields = invoice_to_airtable_fields(
        invoice=invoice,
        source_file=source_file,
        sqlite_invoice_id=sqlite_invoice_id,
    )

    return upsert_record_by_sqlite_id(
        client=client,
        table_name=table_config["invoices"],
        sqlite_id_field="SQLite Invoice ID",
        sqlite_id=sqlite_invoice_id,
        fields=fields,
    )


def sync_quickbooks_draft_to_airtable(
    client,
    draft: QuickBooksBillDraft,
    sqlite_draft_id: int,
) -> dict:
    """Create or update a draft in the configured Airtable table."""

    table_config = get_airtable_table_config()

    fields = quickbooks_draft_to_airtable_fields(
        draft=draft,
        sqlite_draft_id=sqlite_draft_id,
    )

    return upsert_record_by_sqlite_id(
        client=client,
        table_name=table_config["drafts"],
        sqlite_id_field="SQLite Draft ID",
        sqlite_id=sqlite_draft_id,
        fields=fields,
    )
