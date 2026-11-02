import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.schemas import Invoice, QuickBooksBillDraft


def get_connection() -> sqlite3.Connection:
    """
    Establish and return a connection to the SQLite database.

    The database is stored at data/invoices.db
    relative to the project root.
    """

    project_root = Path(__file__).parent.parent
    data_directory = project_root / "data"
    data_directory.mkdir(parents=True, exist_ok=True)

    database_path = data_directory / "invoices.db"

    connection = sqlite3.connect(database_path)

    return connection


def create_table() -> None:
    """Create the invoices table if it doesn't already exist."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_name TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                invoice_number TEXT NOT NULL,
                invoice_date TEXT NOT NULL,
                due_date TEXT,
                currency TEXT NOT NULL,
                line_items TEXT NOT NULL,
                subtotal TEXT NOT NULL,
                tax_amount TEXT,
                total_amount TEXT NOT NULL,
                source_file TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (vendor_name, invoice_number)
            )
        """)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def initialise_database() -> None:
    """Create all required application database tables."""

    create_table()
    create_quickbooks_drafts_table()

def save_invoice(
    invoice: Invoice,
    source_file: str | Path,
) -> int:
    """
    Save a validated Invoice object to the SQLite database.

    Args:
        invoice: Pydantic Invoice object.
        source_file: Path to the original invoice PDF.

    Returns:
        The ID of the newly inserted database record.
    """

    line_items_json = json.dumps(
        [
            item.model_dump(mode="json")
            for item in invoice.line_items
        ]
    )

    invoice_date = invoice.invoice_date.isoformat()

    due_date = (
        invoice.due_date.isoformat()
        if invoice.due_date is not None
        else None
    )

    subtotal = str(invoice.subtotal)

    tax_amount = (
        str(invoice.tax_amount)
        if invoice.tax_amount is not None
        else None
    )

    total_amount = str(invoice.total_amount)

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO invoices (
                vendor_name,
                customer_name,
                invoice_number,
                invoice_date,
                due_date,
                currency,
                line_items,
                subtotal,
                tax_amount,
                total_amount,
                source_file
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            invoice.vendor_name,
            invoice.customer_name,
            invoice.invoice_number,
            invoice_date,
            due_date,
            invoice.currency,
            line_items_json,
            subtotal,
            tax_amount,
            total_amount,
            str(source_file),
        ))

        connection.commit()

        return cursor.lastrowid

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_all_invoices() -> list[Invoice]:
    """Retrieve all invoices and reconstruct them as Invoice objects."""

    connection = get_connection()

    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                vendor_name,
                customer_name,
                invoice_number,
                invoice_date,
                due_date,
                currency,
                line_items,
                subtotal,
                tax_amount,
                total_amount
            FROM invoices
            ORDER BY id ASC
        """)

        rows = cursor.fetchall()

        invoices = []

        for row in rows:
            invoice_data = {
                "vendor_name": row["vendor_name"],
                "customer_name": row["customer_name"],
                "invoice_number": row["invoice_number"],
                "invoice_date": date.fromisoformat(row["invoice_date"]),
                "due_date": (
                    date.fromisoformat(row["due_date"])
                    if row["due_date"] is not None
                    else None
                ),
                "currency": row["currency"],
                "line_items": json.loads(row["line_items"]),
                "subtotal": Decimal(row["subtotal"]),
                "tax_amount": (
                    Decimal(row["tax_amount"])
                    if row["tax_amount"] is not None
                    else None
                ),
                "total_amount": Decimal(row["total_amount"]),
            }

            invoice = Invoice.model_validate(invoice_data)
            invoices.append(invoice)

        return invoices

    finally:
        connection.close()


def create_quickbooks_drafts_table() -> None:
    """Create the QuickBooks bill drafts table if it doesn't exist."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quickbooks_bill_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_name TEXT NOT NULL,
                bill_number TEXT NOT NULL,
                bill_date TEXT NOT NULL,
                due_date TEXT,
                currency TEXT NOT NULL,
                line_items TEXT NOT NULL,
                subtotal TEXT NOT NULL,
                tax_amount TEXT,
                total_amount TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status = 'draft'),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (vendor_name, bill_number)
            )
        """)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def save_quickbooks_draft(
    draft: QuickBooksBillDraft,
) -> int:
    """
    Save a QuickBooks-style bill draft to SQLite.

    Args:
        draft: Validated QuickBooksBillDraft object.

    Returns:
        The ID of the newly inserted draft.
    """

    line_items_json = json.dumps(
        [
            item.model_dump(mode="json")
            for item in draft.line_items
        ]
    )

    bill_date = draft.bill_date.isoformat()

    due_date = (
        draft.due_date.isoformat()
        if draft.due_date is not None
        else None
    )

    subtotal = str(draft.subtotal)

    tax_amount = (
        str(draft.tax_amount)
        if draft.tax_amount is not None
        else None
    )

    total_amount = str(draft.total_amount)

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO quickbooks_bill_drafts (
                vendor_name,
                bill_number,
                bill_date,
                due_date,
                currency,
                line_items,
                subtotal,
                tax_amount,
                total_amount,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            draft.vendor_name,
            draft.bill_number,
            bill_date,
            due_date,
            draft.currency,
            line_items_json,
            subtotal,
            tax_amount,
            total_amount,
            draft.status,
        ))

        connection.commit()

        return cursor.lastrowid

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_all_quickbooks_drafts() -> list[QuickBooksBillDraft]:
    """Retrieve all saved drafts as validated Pydantic objects."""

    connection = get_connection()

    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                vendor_name,
                bill_number,
                bill_date,
                due_date,
                currency,
                line_items,
                subtotal,
                tax_amount,
                total_amount,
                status
            FROM quickbooks_bill_drafts
            ORDER BY id ASC
        """)

        rows = cursor.fetchall()

        drafts = []

        for row in rows:
            draft_data = {
                "vendor_name": row["vendor_name"],
                "bill_number": row["bill_number"],
                "bill_date": date.fromisoformat(row["bill_date"]),
                "due_date": (
                    date.fromisoformat(row["due_date"])
                    if row["due_date"] is not None
                    else None
                ),
                "currency": row["currency"],
                "line_items": json.loads(row["line_items"]),
                "subtotal": Decimal(row["subtotal"]),
                "tax_amount": (
                    Decimal(row["tax_amount"])
                    if row["tax_amount"] is not None
                    else None
                ),
                "total_amount": Decimal(row["total_amount"]),
                "status": row["status"],
            }

            draft = QuickBooksBillDraft.model_validate(draft_data)
            drafts.append(draft)

        return drafts

    finally:
        connection.close()
