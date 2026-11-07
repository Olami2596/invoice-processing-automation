
import sqlite3
import pytest
import src.storage as storage
from src import storage


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Create an isolated database for email tracking tests."""

    db_path = tmp_path / "test_email_processing.db"

    def get_test_connection():
        return sqlite3.connect(db_path)

    monkeypatch.setattr(
        storage,
        "get_connection",
        get_test_connection,
    )

    storage.initialise_database()

    return db_path


@pytest.fixture
def email_data():
    """Provide a unique email record for each test."""

    return {
        "message_id": "test-message-unique-001",
        "subject": "Invoice Submission - INV-TEST-001",
    }


def test_register_email_returns_true_for_new_email(
    test_db,
    email_data,
):
    """A newly registered email should return True."""

    result = storage.register_email(
        email_data["message_id"],
        email_data["subject"],
    )

    assert result is True


def test_register_email_creates_pending_record(
    test_db,
    email_data,
):
    """A new email should initially have pending status."""

    storage.register_email(
        email_data["message_id"],
        email_data["subject"],
    )

    record = storage.get_email_processing_record(
        email_data["message_id"]
    )

    assert record is not None
    assert record["message_id"] == email_data["message_id"]
    assert record["subject"] == email_data["subject"]
    assert record["status"] == "pending"
    assert record["error_message"] is None


def test_register_email_prevents_duplicate_message_ids(
    test_db,
    email_data,
):
    """The same Mailpit message ID must not be inserted twice."""

    first_result = storage.register_email(
        email_data["message_id"],
        email_data["subject"],
    )

    second_result = storage.register_email(
        email_data["message_id"],
        email_data["subject"],
    )

    assert first_result is True
    assert second_result is False


def test_get_email_processing_record_returns_none_for_unknown_email(
    test_db,
):
    """An unregistered email should return None."""

    record = storage.get_email_processing_record(
        "unknown-message-id"
    )

    assert record is None


def test_should_process_new_email(test_db):
    """An email not yet registered should be eligible for processing."""

    assert storage.should_process_email(
        "new-message-id"
    ) is True


def test_should_process_pending_email(test_db, email_data):
    """A pending email should be eligible for processing."""

    storage.register_email(
        email_data["message_id"],
        email_data["subject"],
    )

    assert storage.should_process_email(
        email_data["message_id"]
    ) is True


def test_mark_email_processed(test_db, email_data):
    """A successfully processed email should be marked processed."""

    storage.register_email(
        email_data["message_id"],
        email_data["subject"],
    )

    storage.mark_email_processed(
        email_data["message_id"]
    )

    record = storage.get_email_processing_record(
        email_data["message_id"]
    )

    assert record["status"] == "processed"
    assert record["error_message"] is None


def test_processed_email_should_not_be_processed_again(
    test_db,
    email_data,
):
    """Successfully processed emails should be skipped."""

    storage.register_email(
        email_data["message_id"],
        email_data["subject"],
    )

    storage.mark_email_processed(
        email_data["message_id"]
    )

    assert storage.should_process_email(
        email_data["message_id"]
    ) is False


def test_mark_email_failed_records_error(
    test_db,
    email_data,
):
    """A failed email should retain its error message."""

    storage.register_email(
        email_data["message_id"],
        email_data["subject"],
    )

    error_message = "PDF extraction failed."

    storage.mark_email_failed(
        email_data["message_id"],
        error_message,
    )

    record = storage.get_email_processing_record(
        email_data["message_id"]
    )

    assert record["status"] == "failed"
    assert record["error_message"] == error_message


def test_failed_email_can_be_retried(test_db, email_data):
    """A failed email should remain eligible for processing."""

    storage.register_email(
        email_data["message_id"],
        email_data["subject"],
    )

    storage.mark_email_failed(
        email_data["message_id"],
        "Temporary processing error.",
    )

    assert storage.should_process_email(
        email_data["message_id"]
    ) is True


def test_mark_email_pending_clears_previous_error(
    test_db,
    email_data,
):
    """Retrying a failed email should reset it to pending."""

    storage.register_email(
        email_data["message_id"],
        email_data["subject"],
    )

    storage.mark_email_failed(
        email_data["message_id"],
        "Temporary processing error.",
    )

    storage.mark_email_pending(
        email_data["message_id"]
    )

    record = storage.get_email_processing_record(
        email_data["message_id"]
    )

    assert record["status"] == "pending"
    assert record["error_message"] is None


def test_mark_email_processed_clears_previous_error(
    test_db,
    email_data,
):
    """Successful processing should clear an earlier error."""

    storage.register_email(
        email_data["message_id"],
        email_data["subject"],
    )

    storage.mark_email_failed(
        email_data["message_id"],
        "Previous error.",
    )

    storage.mark_email_processed(
        email_data["message_id"]
    )

    record = storage.get_email_processing_record(
        email_data["message_id"]
    )

    assert record["status"] == "processed"
    assert record["error_message"] is None


def test_mark_email_processed_rejects_unknown_message(test_db):
    """An unregistered email cannot be marked processed."""

    with pytest.raises(LookupError):
        storage.mark_email_processed("unknown-message-id")


def test_mark_email_failed_rejects_unknown_message(test_db):
    """An unregistered email cannot be marked failed."""

    with pytest.raises(LookupError):
        storage.mark_email_failed(
            "unknown-message-id",
            "Something went wrong.",
        )


def test_mark_email_pending_rejects_unknown_message(test_db):
    """An unregistered email cannot be reset to pending."""

    with pytest.raises(LookupError):
        storage.mark_email_pending("unknown-message-id")


def test_email_processing_table_has_unique_message_ids(test_db):
    """The message ID should be the primary key."""

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()

        cursor.execute("""
            PRAGMA table_info(email_processing)
        """)

        columns = cursor.fetchall()

        message_id_column = next(
            column for column in columns
            if column[1] == "message_id"
        )

        assert message_id_column[5] == 1

    finally:
        connection.close()


def test_email_processing_has_valid_status_constraint(test_db):
    """Only the three supported statuses should be accepted."""

    connection = sqlite3.connect(test_db)

    try:
        cursor = connection.cursor()

        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO email_processing (
                    message_id,
                    subject,
                    status
                )
                VALUES (?, ?, ?)
            """, (
                "invalid-status-message",
                "Test email",
                "unknown",
            ))

        connection.rollback()

    finally:
        connection.close()

def test_transient_failed_email_can_be_retried(test_db):
    """A transiently failed email should remain eligible for retry."""

    message_id = "email-retry-001"

    storage.register_email(message_id, "Retry test")

    storage.mark_email_failed(
        message_id,
        "Temporary connection failure",
        failure_type="transient",
    )

    record = storage.get_email_processing_record(message_id)

    assert record["retry_count"] == 1
    assert record["failure_type"] == "transient"
    assert storage.should_process_email(message_id) is True


def test_permanently_failed_email_is_not_retried(test_db):
    """A permanently failed email should not be retried."""

    message_id = "email-permanent-001"

    storage.register_email(message_id, "Permanent test")

    storage.mark_email_failed(
        message_id,
        "Invalid email content",
        failure_type="permanent",
    )

    assert storage.should_process_email(message_id) is False


def test_email_stops_after_three_failed_attempts(test_db):
    """An email should stop being eligible after three failures."""

    message_id = "email-limit-001"

    storage.register_email(message_id, "Retry limit test")

    for attempt in range(storage.MAX_RETRIES):
        storage.mark_email_failed(
            message_id,
            "Temporary processing failure",
            failure_type="transient",
        )

    record = storage.get_email_processing_record(message_id)

    assert record["retry_count"] == storage.MAX_RETRIES
    assert storage.should_process_email(message_id) is False


def test_permanently_failed_attachment_is_not_retried(test_db):
    """A permanently failed attachment should not be retried."""

    message_id = "email-attachment-001"
    part_id = "part-001"

    storage.register_email(message_id, "Attachment test")

    storage.register_email_attachment(
        message_id,
        part_id,
        "invoice.pdf",
    )

    storage.mark_attachment_failed(
        message_id,
        part_id,
        "Corrupted PDF",
        failure_type="permanent",
    )

    assert storage.should_process_attachment(
        message_id,
        part_id,
    ) is False


# ---------------------------------------------------------
# Email retry-limit tests
# ---------------------------------------------------------

def test_new_email_can_be_processed(test_db):
    storage.register_email(
        "retry-new-email-001",
        "New invoice",
    )

    assert storage.should_process_email(
        "retry-new-email-001"
    ) is True


def test_unregistered_email_can_be_processed(test_db):
    assert storage.should_process_email(
        "unregistered-email-001"
    ) is True


def test_processed_email_is_not_processed_again(test_db):
    message_id = "retry-processed-email-001"

    storage.register_email(message_id, "Invoice")
    storage.mark_email_processed(message_id)

    assert storage.should_process_email(message_id) is False


@pytest.mark.parametrize(
    "retry_count",
    [1, 2],
)
def test_transient_failed_email_can_be_retried(
    test_db,
    retry_count,
):
    message_id = f"retry-transient-email-{retry_count}"

    storage.register_email(message_id, "Invoice")

    for _ in range(retry_count):
        storage.mark_email_failed(
            message_id,
            "Temporary processing error",
            failure_type="transient",
        )

    assert storage.should_process_email(message_id) is True


@pytest.mark.parametrize(
    "retry_count",
    [3, 4],
)
def test_transient_failed_email_stops_after_retry_limit(
    test_db,
    retry_count,
):
    message_id = f"retry-exhausted-email-{retry_count}"

    storage.register_email(message_id, "Invoice")

    for _ in range(retry_count):
        storage.mark_email_failed(
            message_id,
            "Temporary processing error",
            failure_type="transient",
        )

    assert storage.should_process_email(message_id) is False


def test_permanently_failed_email_is_not_retried(test_db):
    message_id = "retry-permanent-email-001"

    storage.register_email(message_id, "Invoice")

    storage.mark_email_failed(
        message_id,
        "Invalid invoice attachment",
        failure_type="permanent",
    )

    assert storage.should_process_email(message_id) is False


# ---------------------------------------------------------
# Attachment retry-limit tests
# ---------------------------------------------------------

def register_test_attachment(message_id, part_id):
    storage.register_email(message_id, "Invoice")

    storage.register_email_attachment(
        message_id,
        part_id,
        "test_invoice.pdf",
    )


def test_new_attachment_can_be_processed(test_db):
    message_id = "retry-new-attachment-001"
    part_id = "part-001"

    register_test_attachment(message_id, part_id)

    assert storage.should_process_attachment(
        message_id,
        part_id,
    ) is True


def test_unregistered_attachment_can_be_processed(test_db):
    assert storage.should_process_attachment(
        "unknown-email-001",
        "unknown-part-001",
    ) is True


def test_processed_attachment_is_not_processed_again(test_db):
    message_id = "retry-processed-attachment-001"
    part_id = "part-001"

    register_test_attachment(message_id, part_id)

    storage.mark_attachment_processed(message_id, part_id)

    assert storage.should_process_attachment(
        message_id,
        part_id,
    ) is False


@pytest.mark.parametrize(
    "retry_count",
    [1, 2],
)
def test_transient_failed_attachment_can_be_retried(
    test_db,
    retry_count,
):
    message_id = f"retry-transient-attachment-{retry_count}"
    part_id = "part-001"

    register_test_attachment(message_id, part_id)

    for _ in range(retry_count):
        storage.mark_attachment_failed(
            message_id,
            part_id,
            "Temporary extraction error",
            failure_type="transient",
        )

    assert storage.should_process_attachment(
        message_id,
        part_id,
    ) is True


@pytest.mark.parametrize(
    "retry_count",
    [3, 4],
)
def test_transient_failed_attachment_stops_after_retry_limit(
    test_db,
    retry_count,
):
    message_id = f"retry-exhausted-attachment-{retry_count}"
    part_id = "part-001"

    register_test_attachment(message_id, part_id)

    for _ in range(retry_count):
        storage.mark_attachment_failed(
            message_id,
            part_id,
            "Temporary extraction error",
            failure_type="transient",
        )

    assert storage.should_process_attachment(
        message_id,
        part_id,
    ) is False


def test_permanently_failed_attachment_is_not_retried(test_db):
    message_id = "retry-permanent-attachment-001"
    part_id = "part-001"

    register_test_attachment(message_id, part_id)

    storage.mark_attachment_failed(
        message_id,
        part_id,
        "Corrupted PDF",
        failure_type="permanent",
    )

    assert storage.should_process_attachment(
        message_id,
        part_id,
    ) is False
