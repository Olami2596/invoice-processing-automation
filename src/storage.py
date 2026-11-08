import json
import uuid
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from src.schemas import Invoice, QuickBooksBillDraft

MAX_RETRIES = 3
MAX_AIRTABLE_RETRIES = 5

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
    create_email_processing_table()
    create_email_attachments_table()
    create_airtable_sync_table()
    migrate_retry_tracking_columns()

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


def create_airtable_sync_table() -> None:
    """Create the persistent Airtable synchronization queue."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS airtable_sync (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                entity_type TEXT NOT NULL
                    CHECK (
                        entity_type IN (
                            'invoice',
                            'quickbooks_draft'
                        )
                    ),

                local_record_id INTEGER NOT NULL,

                airtable_record_id TEXT,

                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (
                        status IN (
                            'pending',
                            'synced',
                            'failed'
                        )
                    ),

                retry_count INTEGER NOT NULL DEFAULT 0
                    CHECK (retry_count >= 0),

                error_message TEXT,

                failure_type TEXT
                    CHECK (
                        failure_type IS NULL
                        OR failure_type IN ('transient', 'permanent')
                    ),

                next_retry_at TEXT,

                manual_retry INTEGER NOT NULL DEFAULT 0
                    CHECK (manual_retry IN (0, 1)),

                claim_token TEXT,
                claimed_at TEXT,
                claim_expires_at TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                UNIQUE (entity_type, local_record_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_airtable_sync_status
            ON airtable_sync (status, created_at)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_airtable_sync_retry
            ON airtable_sync (status, failure_type, next_retry_at)
        """)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

def create_email_processing_table() -> None:
    """Create the email processing tracking table."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_processing (

                message_id TEXT PRIMARY KEY,

                subject TEXT NOT NULL,

                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (
                        status IN ('pending', 'processed', 'failed')
                    ),

                error_message TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            )
        """)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

def create_email_attachments_table() -> None:
    """Create the table used to track individual email attachments."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_attachments (
                message_id TEXT NOT NULL,
                part_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (
                        status IN (
                            'pending',
                            'downloaded',
                            'processed',
                            'failed'
                        )
                    ),
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                PRIMARY KEY (message_id, part_id),

                FOREIGN KEY (message_id)
                    REFERENCES email_processing(message_id)
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

def save_invoice_and_quickbooks_draft(
    invoice: Invoice,
    source_file: str | Path,
    draft: QuickBooksBillDraft,
) -> tuple[int, int]:
    """
    Save an invoice and its QuickBooks draft atomically.

    Both records are committed together. If either insertion fails,
    the entire transaction is rolled back.

    Returns:
        A tuple containing (invoice_id, draft_id).
    """

    invoice_line_items = json.dumps(
        [
            item.model_dump(mode="json")
            for item in invoice.line_items
        ]
    )

    draft_line_items = json.dumps(
        [
            item.model_dump(mode="json")
            for item in draft.line_items
        ]
    )

    connection = get_connection()

    try:
        cursor = connection.cursor()

        # Insert the invoice.
        cursor.execute(
            """
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
            """,
            (
                invoice.vendor_name,
                invoice.customer_name,
                invoice.invoice_number,
                invoice.invoice_date.isoformat(),
                (
                    invoice.due_date.isoformat()
                    if invoice.due_date is not None
                    else None
                ),
                invoice.currency,
                invoice_line_items,
                str(invoice.subtotal),
                (
                    str(invoice.tax_amount)
                    if invoice.tax_amount is not None
                    else None
                ),
                str(invoice.total_amount),
                str(source_file),
            ),
        )

        invoice_id = cursor.lastrowid

        # Insert the corresponding QuickBooks draft.
        cursor.execute(
            """
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
            """,
            (
                draft.vendor_name,
                draft.bill_number,
                draft.bill_date.isoformat(),
                (
                    draft.due_date.isoformat()
                    if draft.due_date is not None
                    else None
                ),
                draft.currency,
                draft_line_items,
                str(draft.subtotal),
                (
                    str(draft.tax_amount)
                    if draft.tax_amount is not None
                    else None
                ),
                str(draft.total_amount),
                draft.status,
            ),
        )


        draft_id = cursor.lastrowid

        # Add the invoice to the Airtable synchronization queue.
        cursor.execute(
            """
            INSERT INTO airtable_sync (
                entity_type,
                local_record_id,
                status
            )
            VALUES (?, ?, 'pending')
            """,
            ("invoice", invoice_id),
        )

        # Add the QuickBooks draft to the Airtable synchronization queue.
        cursor.execute(
            """
            INSERT INTO airtable_sync (
                entity_type,
                local_record_id,
                status
            )
            VALUES (?, ?, 'pending')
            """,
            ("quickbooks_draft", draft_id),
        )

        # Commit invoices, draft, and synchronization jobs together.
        connection.commit()


        return invoice_id, draft_id

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


def register_email(message_id: str, subject: str) -> bool:
    """
    Register an email for processing.

    Returns:
        True if the email was newly registered.
        False if the message ID already exists.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO email_processing (
                message_id,
                subject,
                status
            )
            VALUES (?, ?, 'pending')
        """, (message_id, subject))

        connection.commit()

        return cursor.rowcount == 1

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_email_processing_record(message_id: str) -> dict | None:
    """
    Retrieve an email's processing record.

    Returns None if the message has not been registered.
    """

    connection = get_connection()

    try:
        connection.row_factory = sqlite3.Row

        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                message_id,
                subject,
                status,
                error_message,
                retry_count,
                failure_type,
                created_at,
                updated_at
            FROM email_processing
            WHERE message_id = ?
        """, (message_id,))

        row = cursor.fetchone()

        return dict(row) if row is not None else None

    finally:
        connection.close()


def should_process_email(message_id: str) -> bool:
    """
    Determine whether an email is eligible for processing.

    Process new and pending emails.
    Skip processed emails.
    Skip permanent failures.
    Stop retrying after MAX_RETRIES failed attempts.
    """

    record = get_email_processing_record(message_id)

    if record is None:
        return True

    if record["status"] == "processed":
        return False

    if record["status"] != "failed":
        return True

    if record["failure_type"] == "permanent":
        return False

    return record["retry_count"] < MAX_RETRIES


def mark_email_pending(message_id: str) -> None:
    """
    Reset a failed email to pending for manual recovery.

    Processed emails cannot be reset.
    Retry count is preserved.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE email_processing
            SET
                status = 'pending',
                error_message = NULL,
                failure_type = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE message_id = ?
              AND status = 'failed'
        """, (message_id,))

        if cursor.rowcount == 0:
            record = get_email_processing_record(message_id)

            if record is None:
                raise LookupError(
                    f"Email has not been registered: {message_id}"
                )

            if record["status"] == "processed":
                raise ValueError(
                    "A processed email cannot be reset to pending."
                )

            raise ValueError(
                "Only failed emails can be manually reset."
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

def mark_email_processed(message_id: str) -> None:
    """
    Mark an email as successfully processed.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE email_processing
            SET
                status = 'processed',
                error_message = NULL,
                failure_type = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE message_id = ?
        """, (message_id,))

        if cursor.rowcount == 0:
            raise LookupError(
                f"Email has not been registered: {message_id}"
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def mark_email_failed(
    message_id: str,
    error_message: str,
    failure_type: str = "transient",
) -> None:
    """
    Mark an email as failed and record its failure classification.

    Each failed attempt increments retry_count.
    """

    if failure_type not in {"transient", "permanent"}:
        raise ValueError(
            "failure_type must be 'transient' or 'permanent'"
        )

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE email_processing
            SET
                status = 'failed',
                error_message = ?,
                failure_type = ?,
                retry_count = retry_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE message_id = ?
        """, (error_message, failure_type, message_id))

        if cursor.rowcount == 0:
            raise LookupError(
                f"Email has not been registered: {message_id}"
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

def register_email_attachment(
    message_id: str,
    part_id: str,
    filename: str,
) -> bool:
    """
    Register an attachment belonging to an email.

    Returns True if newly registered, otherwise False.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO email_attachments (
                message_id,
                part_id,
                filename,
                status
            )
            VALUES (?, ?, ?, 'pending')
        """, (message_id, part_id, filename))

        connection.commit()

        return cursor.rowcount == 1

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_email_attachment_record(
    message_id: str,
    part_id: str,
) -> dict | None:
    """Retrieve the tracking record for one email attachment."""

    connection = get_connection()

    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                message_id,
                part_id,
                filename,
                file_path,
                status,
                error_message,
                retry_count,
                failure_type,
                created_at,
                updated_at
            FROM email_attachments
            WHERE message_id = ? AND part_id = ?
        """, (message_id, part_id))

        row = cursor.fetchone()

        return dict(row) if row is not None else None

    finally:
        connection.close()


def mark_attachment_downloaded(
    message_id: str,
    part_id: str,
    file_path: str,
) -> None:
    """Record the successful download location of an attachment."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE email_attachments
            SET
                file_path = ?,
                status = 'downloaded',
                error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE message_id = ? AND part_id = ?
        """, (file_path, message_id, part_id))

        if cursor.rowcount == 0:
            raise LookupError(
                f"Attachment has not been registered: {message_id}/{part_id}"
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def mark_attachment_processed(
    message_id: str,
    part_id: str,
) -> None:
    """Mark an attachment as successfully processed."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE email_attachments
            SET
                status = 'processed',
                error_message = NULL,
                failure_type = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE message_id = ? AND part_id = ?
        """, (message_id, part_id))

        if cursor.rowcount == 0:
            raise LookupError(
                f"Attachment has not been registered: {message_id}/{part_id}"
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def mark_attachment_failed(
    message_id: str,
    part_id: str,
    error_message: str,
    failure_type: str = "transient",
) -> None:
    """
    Mark an attachment as failed and record its failure classification.

    Each failed attempt increments retry_count.
    """

    if failure_type not in {"transient", "permanent"}:
        raise ValueError(
            "failure_type must be 'transient' or 'permanent'"
        )

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE email_attachments
            SET
                status = 'failed',
                error_message = ?,
                failure_type = ?,
                retry_count = retry_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE message_id = ? AND part_id = ?
        """, (
            error_message,
            failure_type,
            message_id,
            part_id,
        ))

        if cursor.rowcount == 0:
            raise LookupError(
                f"Attachment has not been registered: "
                f"{message_id}/{part_id}"
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

def get_email_attachments(message_id: str) -> list[dict]:
    """Retrieve all tracked attachments belonging to an email."""

    connection = get_connection()

    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                message_id,
                part_id,
                filename,
                file_path,
                status,
                error_message,
                retry_count,
                failure_type,
                created_at,
                updated_at
            FROM email_attachments
            WHERE message_id = ?
            ORDER BY created_at ASC
        """, (message_id,))

        return [dict(row) for row in cursor.fetchall()]

    finally:
        connection.close()

def should_process_attachment(
    message_id: str,
    part_id: str,
) -> bool:
    """
    Determine whether an attachment is eligible for processing.

    Process pending and downloaded attachments.
    Skip processed attachments.
    Skip permanent failures.
    Stop retrying after MAX_RETRIES failed attempts.
    """

    record = get_email_attachment_record(message_id, part_id)

    if record is None:
        return True

    if record["status"] == "processed":
        return False

    if record["status"] != "failed":
        return True

    if record["failure_type"] == "permanent":
        return False

    return record["retry_count"] < MAX_RETRIES

def mark_attachment_pending(
    message_id: str,
    part_id: str,
) -> None:
    """
    Reset a failed attachment to pending for manual recovery.

    Processed attachments cannot be reset.
    Retry count is preserved.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE email_attachments
            SET
                status = 'pending',
                error_message = NULL,
                failure_type = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE message_id = ?
              AND part_id = ?
              AND status = 'failed'
        """, (message_id, part_id))

        if cursor.rowcount == 0:
            record = get_email_attachment_record(
                message_id,
                part_id,
            )

            if record is None:
                raise LookupError(
                    f"Attachment has not been registered: "
                    f"{message_id}/{part_id}"
                )

            if record["status"] == "processed":
                raise ValueError(
                    "A processed attachment cannot be reset to pending."
                )

            raise ValueError(
                "Only failed attachments can be manually reset."
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

def migrate_retry_tracking_columns():
    """
    Add retry tracking columns to existing email and Airtable tables.

    Existing records are preserved.
    Newly added columns receive safe default values.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        tables = [
            "email_processing",
            "email_attachments",
            "airtable_sync",
        ]

        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")

            existing_columns = {
                row[1] for row in cursor.fetchall()
            }

            if "retry_count" not in existing_columns:
                cursor.execute(
                    f"""
                    ALTER TABLE {table}
                    ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0
                    """
                )

            if "failure_type" not in existing_columns:
                cursor.execute(
                    f"""
                    ALTER TABLE {table}
                    ADD COLUMN failure_type TEXT
                    """
                )

            if table == "airtable_sync":
                if "next_retry_at" not in existing_columns:
                    cursor.execute("""
                        ALTER TABLE airtable_sync
                        ADD COLUMN next_retry_at TEXT
                    """)

                if "manual_retry" not in existing_columns:
                    cursor.execute("""
                        ALTER TABLE airtable_sync
                        ADD COLUMN manual_retry INTEGER NOT NULL DEFAULT 0
                    """)

                if "claim_token" not in existing_columns:
                    cursor.execute("""
                        ALTER TABLE airtable_sync
                        ADD COLUMN claim_token TEXT
                    """)

                if "claimed_at" not in existing_columns:
                    cursor.execute("""
                        ALTER TABLE airtable_sync
                        ADD COLUMN claimed_at TEXT
                    """)

                if "claim_expires_at" not in existing_columns:
                    cursor.execute("""
                        ALTER TABLE airtable_sync
                        ADD COLUMN claim_expires_at TEXT
                    """)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_airtable_sync_job(job_id: int) -> dict | None:
    """Retrieve one Airtable synchronization job."""

    if job_id <= 0:
        raise ValueError("job_id must be positive.")

    connection = get_connection()

    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        cursor.execute("""
            SELECT *
            FROM airtable_sync
            WHERE id = ?
        """, (job_id,))

        row = cursor.fetchone()

        return dict(row) if row is not None else None

    finally:
        connection.close()


def claim_airtable_sync_job(job_id: int, lease_seconds: int = 120) -> str | None:
    """
    Atomically claim a pending Airtable sync job.

    Returns a unique claim token if successful.
    Returns None if the job does not exist, is not pending,
    or is currently claimed by another worker.
    """
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be greater than zero.")

    claim_token = uuid.uuid4().hex

    now = datetime.now(timezone.utc)
    claimed_at = now.isoformat()
    claim_expires_at = (
        now + timedelta(seconds=lease_seconds)
    ).isoformat()

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        cursor = connection.execute(
            """
            UPDATE airtable_sync
            SET
                claim_token = ?,
                claimed_at = ?,
                claim_expires_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'pending'
              AND (
                  claim_token IS NULL
                  OR claim_expires_at IS NULL
                  OR claim_expires_at <= ?
              )
            """,
            (
                claim_token,
                claimed_at,
                claim_expires_at,
                job_id,
                claimed_at,
            ),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return None

        connection.commit()
        return claim_token

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_pending_airtable_sync_jobs(
    limit: int = 100,
) -> list[dict]:
    """Retrieve pending Airtable jobs that are available to be claimed."""

    if limit < 1:
        raise ValueError("limit must be greater than zero.")

    now = datetime.now(timezone.utc).isoformat()

    connection = get_connection()

    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        cursor.execute("""
            SELECT *
            FROM airtable_sync
            WHERE status = 'pending'
              AND (
                  claim_token IS NULL
                  OR claim_expires_at IS NULL
                  OR claim_expires_at <= ?
              )
            ORDER BY created_at ASC, id ASC
            LIMIT ?
        """, (now, limit))

        return [dict(row) for row in cursor.fetchall()]

    finally:
        connection.close()


def mark_airtable_sync_synced(
    job_id: int,
    airtable_record_id: str,
    claim_token: str,
) -> None:
    """Mark an Airtable sync job as successful using its active claim."""

    if job_id <= 0:
        raise ValueError("job_id must be a positive integer.")

    if not airtable_record_id or not airtable_record_id.strip():
        raise ValueError("airtable_record_id cannot be empty.")

    if not claim_token or not claim_token.strip():
        raise ValueError("claim_token cannot be empty.")

    connection = get_connection()

    try:
        cursor = connection.cursor()

        connection.execute("BEGIN IMMEDIATE")

        # Check whether the job already exists and whether it was
        # successfully synced with this exact Airtable record ID.
        cursor.execute(
            """
            SELECT status, airtable_record_id
            FROM airtable_sync
            WHERE id = ?
            """,
            (job_id,),
        )

        record = cursor.fetchone()

        if record is None:
            raise LookupError(
                f"Airtable sync job {job_id} does not exist."
            )

        # Preserve idempotency: repeating the same successful operation
        # should not cause an error.
        if (
            record[0] == "synced"
            and record[1] == airtable_record_id
        ):
            connection.commit()
            return

        current_time = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            UPDATE airtable_sync
            SET
                status = 'synced',
                airtable_record_id = ?,
                error_message = NULL,
                failure_type = NULL,
                next_retry_at = NULL,
                manual_retry = 0,
                claim_token = NULL,
                claimed_at = NULL,
                claim_expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE
                id = ?
                AND status = 'pending'
                AND claim_token = ?
                AND claim_expires_at > ?
            """,
            (
                airtable_record_id,
                job_id,
                claim_token,
                current_time,
            ),
        )

        if cursor.rowcount != 1:
            raise ValueError(
                "Job cannot be marked as synced: "
                "claim is missing, expired, or no longer valid."
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()



def mark_airtable_sync_failed(
    job_id: int,
    error_message: str,
    claim_token: str,
    failure_type: str = "transient",
) -> None:
    """
    Mark a claimed Airtable job as failed.

    Transient failures receive an exponential backoff schedule.
    Permanent failures are never automatically retried.
    """

    if job_id <= 0:
        raise ValueError("job_id must be positive.")

    if not error_message or not error_message.strip():
        raise ValueError("error_message cannot be empty.")

    if not claim_token or not claim_token.strip():
        raise ValueError("claim_token cannot be empty.")

    if failure_type not in {"transient", "permanent"}:
        raise ValueError(
            "failure_type must be 'transient' or 'permanent'."
        )

    now = datetime.now(timezone.utc).isoformat()

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT retry_count
            FROM airtable_sync
            WHERE id = ?
              AND status = 'pending'
              AND claim_token = ?
              AND claim_expires_at > ?
            """,
            (job_id, claim_token, now),
        )

        record = cursor.fetchone()

        if record is None:
            existing = get_airtable_sync_job(job_id)

            if existing is None:
                raise LookupError(
                    f"Airtable sync job not found: {job_id}"
                )

            raise ValueError(
                "Job cannot be marked as failed: "
                "claim is missing, expired, or no longer valid."
            )

        next_retry_count = record[0] + 1
        next_retry_at = None

        if (
            failure_type == "transient"
            and next_retry_count < MAX_AIRTABLE_RETRIES
        ):
            delay_minutes = 2 ** (next_retry_count - 1)

            next_retry_at = (
                datetime.now(timezone.utc)
                + timedelta(minutes=delay_minutes)
            ).isoformat()

        cursor.execute(
            """
            UPDATE airtable_sync
            SET
                status = 'failed',
                error_message = ?,
                failure_type = ?,
                retry_count = ?,
                next_retry_at = ?,
                manual_retry = 0,
                claim_token = NULL,
                claimed_at = NULL,
                claim_expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'pending'
              AND claim_token = ?
              AND claim_expires_at > ?
            """,
            (
                error_message,
                failure_type,
                next_retry_count,
                next_retry_at,
                job_id,
                claim_token,
                now,
            ),
        )

        if cursor.rowcount != 1:
            raise ValueError(
                "Job claim became invalid before failure could be recorded."
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def mark_airtable_sync_pending(job_id: int) -> None:
    """Manually reset a failed job while preserving its retry history."""

    if job_id <= 0:
        raise ValueError("job_id must be positive.")

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE airtable_sync
            SET
                status = 'pending',
                error_message = NULL,
                failure_type = NULL,
                next_retry_at = NULL,
                manual_retry = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'failed'
        """, (job_id,))

        if cursor.rowcount == 0:
            cursor.execute(
                "SELECT status FROM airtable_sync WHERE id = ?",
                (job_id,),
            )
            record = cursor.fetchone()

            if record is None:
                raise LookupError(
                    f"Airtable sync job not found: {job_id}"
                )

            raise ValueError(
                "Only failed jobs can be manually reset."
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_invoice_by_id(invoice_id: int) -> tuple[Invoice, str] | None:
    """Retrieve an invoice and its source file using its SQLite ID."""

    if invoice_id <= 0:
        raise ValueError("invoice_id must be positive.")

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
                total_amount,
                source_file
            FROM invoices
            WHERE id = ?
        """, (invoice_id,))

        row = cursor.fetchone()

        if row is None:
            return None

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

        return invoice, row["source_file"]

    finally:
        connection.close()


def get_quickbooks_draft_by_id(
    draft_id: int,
) -> QuickBooksBillDraft | None:
    """Retrieve a QuickBooks draft using its SQLite ID."""

    if draft_id <= 0:
        raise ValueError("draft_id must be positive.")

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
            WHERE id = ?
        """, (draft_id,))

        row = cursor.fetchone()

        if row is None:
            return None

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

        return QuickBooksBillDraft.model_validate(draft_data)

    finally:
        connection.close()

def promote_due_airtable_sync_retries(limit: int = 100) -> int:
    """Move eligible failed Airtable jobs back to the pending queue."""

    if limit <= 0:
        raise ValueError("Limit must be greater than zero.")

    now = datetime.now(timezone.utc).isoformat()

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE airtable_sync
            SET
                status = 'pending',
                error_message = NULL,
                failure_type = NULL,
                next_retry_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id IN (
                SELECT id
                FROM airtable_sync
                WHERE
                    status = 'failed'
                    AND failure_type = 'transient'
                    AND retry_count < ?
                    AND next_retry_at IS NOT NULL
                    AND next_retry_at <= ?
                ORDER BY next_retry_at ASC, id ASC
                LIMIT ?
            )
            """,
            (MAX_AIRTABLE_RETRIES, now, limit),
        )

        promoted_count = cursor.rowcount

        connection.commit()

        return promoted_count

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
