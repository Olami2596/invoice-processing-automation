import json
import uuid
import sqlite3
import pytest
import logging
from src import email_ingestion
import src.storage as storage


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Create an isolated database for email ingestion tests."""

    db_path = tmp_path / "test_email_ingestion.db"

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
def invoice_number():
    """Generate a unique invoice number for each test."""
    return f"INV-TEST-{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture
def valid_pdf():
    """Provide minimal PDF-like bytes for testing."""
    return b"%PDF-1.4\nMock PDF content\n%%EOF"


@pytest.fixture
def mock_mailpit_api(monkeypatch, invoice_number, valid_pdf):
    message_id = "test-message-123"
    part_id = "test-part-456"

    message_summary = {
        "ID": message_id,
        "Subject": f"Invoice Submission - {invoice_number}",
    }

    message_details = {
        "ID": message_id,
        "Subject": f"Invoice Submission - {invoice_number}",
        "Attachments": [
            {
                "FileName": f"{invoice_number}.pdf",
                "ContentType": "application/pdf",
                "PartID": part_id,
            }
        ],
    }

    def fake_api_get(url):
        if "/search?" in url:
            return json.dumps({
                "messages": [message_summary]
            }).encode("utf-8")

        # Check attachment URL before general message URL.
        if f"/message/{message_id}/part/{part_id}" in url:
            return valid_pdf

        if f"/message/{message_id}" in url:
            return json.dumps(message_details).encode("utf-8")

        raise ValueError(f"Unexpected API URL: {url}")

    monkeypatch.setattr(email_ingestion, "api_get", fake_api_get)

    monkeypatch.setattr(
        email_ingestion,
        "get_mailpit_api_url",
        lambda: "http://localhost:8025/api/v1",
    )

    return message_id


def test_successful_email_ingestion(
    tmp_path,
    invoice_number,
    mock_mailpit_api,
):
    """Verify that an invoice PDF is successfully downloaded."""

    downloaded_files = email_ingestion.ingest_invoice_email(
        invoice_number,
        output_directory=tmp_path,
    )

    assert len(downloaded_files) == 1

    downloaded_file = downloaded_files[0]

    assert downloaded_file.exists()
    assert downloaded_file.name == f"{invoice_number}.pdf"
    assert downloaded_file.read_bytes().startswith(b"%PDF-")


def test_email_not_found(tmp_path, monkeypatch, invoice_number):
    """Verify that a missing email raises LookupError."""

    monkeypatch.setattr(
        email_ingestion,
        "get_mailpit_api_url",
        lambda: "http://localhost:8025/api/v1",
    )

    monkeypatch.setattr(
        email_ingestion,
        "api_get",
        lambda url: json.dumps({"messages": []}).encode("utf-8"),
    )

    with pytest.raises(LookupError):
        email_ingestion.ingest_invoice_email(
            invoice_number,
            output_directory=tmp_path,
        )


def test_email_without_pdf_attachment(
    tmp_path,
    monkeypatch,
    invoice_number,
):
    """Verify that an email without PDF attachments is rejected."""

    message_id = "message-without-pdf"

    search_response = {
        "messages": [
            {
                "ID": message_id,
                "Subject": f"Invoice Submission - {invoice_number}",
            }
        ]
    }

    message_details = {
        "ID": message_id,
        "Subject": f"Invoice Submission - {invoice_number}",
        "Attachments": [
            {
                "FileName": "notes.txt",
                "ContentType": "text/plain",
                "PartID": "text-part",
            }
        ],
    }

    def fake_api_get(url):
        if "/search?" in url:
            return json.dumps(search_response).encode("utf-8")

        if f"/message/{message_id}" in url:
            return json.dumps(message_details).encode("utf-8")

        raise ValueError(f"Unexpected API URL: {url}")

    monkeypatch.setattr(email_ingestion, "api_get", fake_api_get)

    monkeypatch.setattr(
        email_ingestion,
        "get_mailpit_api_url",
        lambda: "http://localhost:8025/api/v1",
    )

    with pytest.raises(FileNotFoundError):
        email_ingestion.ingest_invoice_email(
            invoice_number,
            output_directory=tmp_path,
        )


def test_multiple_pdf_attachments(
    tmp_path,
    monkeypatch,
    invoice_number,
):
    """Verify that all PDF attachments are downloaded."""

    message_id = "multiple-attachments-message"

    attachments = [
        {
            "FileName": "invoice-copy-1.pdf",
            "ContentType": "application/pdf",
            "PartID": "part-1",
        },
        {
            "FileName": "invoice-copy-2.pdf",
            "ContentType": "application/pdf",
            "PartID": "part-2",
        },
    ]

    def fake_api_get(url):
        if "/search?" in url:
            return json.dumps({
                "messages": [
                    {
                        "ID": message_id,
                        "Subject": f"Invoice Submission - {invoice_number}",
                    }
                ]
            }).encode("utf-8")

        # Specific attachment URLs must be checked first.
        if "/part/part-1" in url:
            return b"%PDF-1.4\nFirst PDF\n%%EOF"

        if "/part/part-2" in url:
            return b"%PDF-1.4\nSecond PDF\n%%EOF"

        if f"/message/{message_id}" in url:
            return json.dumps({
                "ID": message_id,
                "Attachments": attachments,
            }).encode("utf-8")

        raise ValueError(f"Unexpected API URL: {url}")

    monkeypatch.setattr(email_ingestion, "api_get", fake_api_get)

    monkeypatch.setattr(
        email_ingestion,
        "get_mailpit_api_url",
        lambda: "http://localhost:8025/api/v1",
    )

    downloaded_files = email_ingestion.ingest_invoice_email(
        invoice_number,
        output_directory=tmp_path,
    )

    assert len(downloaded_files) == 2
    assert (tmp_path / "invoice-copy-1.pdf").exists()
    assert (tmp_path / "invoice-copy-2.pdf").exists()


def test_invalid_pdf_attachment(
    tmp_path,
    monkeypatch,
    invoice_number,
):
    """Verify that non-PDF content is rejected."""

    message_id = "invalid-pdf-message"

    def fake_api_get(url):
        if "/search?" in url:
            return json.dumps({
                "messages": [
                    {
                        "ID": message_id,
                        "Subject": f"Invoice Submission - {invoice_number}",
                    }
                ]
            }).encode("utf-8")

        if "/part/invalid-part" in url:
            return b"This is not a PDF file."

        if f"/message/{message_id}" in url:
            return json.dumps({
                "ID": message_id,
                "Attachments": [
                    {
                        "FileName": "invoice.pdf",
                        "ContentType": "application/pdf",
                        "PartID": "invalid-part",
                    }
                ],
            }).encode("utf-8")

        raise ValueError(f"Unexpected API URL: {url}")

    monkeypatch.setattr(email_ingestion, "api_get", fake_api_get)

    monkeypatch.setattr(
        email_ingestion,
        "get_mailpit_api_url",
        lambda: "http://localhost:8025/api/v1",
    )

    with pytest.raises(ValueError, match="not a valid PDF"):
        email_ingestion.ingest_invoice_email(
            invoice_number,
            output_directory=tmp_path,
        )



def test_duplicate_download_protection(
    tmp_path,
    invoice_number,
    mock_mailpit_api,
):
    """Verify that existing attachments are not overwritten."""

    existing_file = tmp_path / f"{invoice_number}.pdf"
    existing_content = b"Existing file content"

    existing_file.write_bytes(existing_content)

    downloaded_files = email_ingestion.ingest_invoice_email(
        invoice_number,
        output_directory=tmp_path,
    )

    assert len(downloaded_files) == 1

    downloaded_file = downloaded_files[0]

    assert downloaded_file.name == f"{invoice_number}_1.pdf"
    assert downloaded_file.exists()

    # The original file must remain unchanged.
    assert existing_file.read_bytes() == existing_content


def test_ingest_recent_invoice_emails(
    tmp_path,
    monkeypatch,
    invoice_number,
    test_db,
):
    """Verify that recent invoice emails are discovered and downloaded."""

    message_id = "recent-invoice-message"

    messages = [
        {
            "ID": message_id,
            "Subject": f"Invoice Submission - {invoice_number}",
        }
    ]

    attachments = [
        {
            "FileName": f"{invoice_number}.pdf",
            "ContentType": "application/pdf",
            "PartID": "recent-invoice-part",
        }
    ]

    def fake_get_recent_emails(start=0, limit=50):
        assert start == 0
        assert limit == 10
        return messages

    def fake_get_email_details(received_message_id):
        assert received_message_id == message_id

        return {
            "ID": message_id,
            "Attachments": attachments,
        }

    def fake_api_get(url):
        if "/part/recent-invoice-part" in url:
            return b"%PDF-1.4\nFresh invoice PDF\n%%EOF"

        raise ValueError(f"Unexpected API URL: {url}")

    monkeypatch.setattr(
        email_ingestion,
        "get_recent_emails",
        fake_get_recent_emails,
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_email_details",
        fake_get_email_details,
    )

    monkeypatch.setattr(
        email_ingestion,
        "api_get",
        fake_api_get,
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_mailpit_api_url",
        lambda: "http://localhost:8025/api/v1",
    )

    results = email_ingestion.ingest_recent_invoice_emails(
        start=0,
        limit=10,
        output_directory=tmp_path,
    )

    assert len(results) == 1

    result = results[0]

    assert result["message_id"] == message_id
    assert invoice_number in result["subject"]

    assert len(result["downloaded_files"]) == 1

    downloaded_file = result["downloaded_files"][0]

    assert downloaded_file.exists()
    assert downloaded_file.name == f"{invoice_number}.pdf"
    assert downloaded_file.read_bytes().startswith(b"%PDF-")


def test_ingest_recent_emails_skips_emails_without_pdf(
    tmp_path,
    monkeypatch,
    test_db,
):
    """Verify that emails without PDF attachments are skipped."""

    messages = [
        {
            "ID": "text-message-123",
            "Subject": "Meeting Notes",
        }
    ]

    monkeypatch.setattr(
        email_ingestion,
        "get_recent_emails",
        lambda start=0, limit=50: messages,
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_email_details",
        lambda message_id: {
            "ID": message_id,
            "Attachments": [
                {
                    "FileName": "notes.txt",
                    "ContentType": "text/plain",
                    "PartID": "text-part",
                }
            ],
        },
    )

    results = email_ingestion.ingest_recent_invoice_emails(
        output_directory=tmp_path,
    )

    assert results == []
    assert not list(tmp_path.glob("*.pdf"))


def test_ingest_recent_emails_skips_messages_without_id(
    tmp_path,
    monkeypatch,
):
    """Verify that messages without IDs are ignored."""

    messages = [
        {
            "Subject": "Invoice Submission",
        }
    ]

    monkeypatch.setattr(
        email_ingestion,
        "get_recent_emails",
        lambda start=0, limit=50: messages,
    )

    results = email_ingestion.ingest_recent_invoice_emails(
        output_directory=tmp_path,
    )

    assert results == []
    assert list(tmp_path.iterdir()) == []


def test_ingestion_skips_already_processed_email(
    tmp_path,
    monkeypatch,
):
    """Successfully processed emails should not be downloaded again."""

    message_id = "already-processed-message"

    monkeypatch.setattr(
        email_ingestion,
        "get_recent_emails",
        lambda start=0, limit=50: [
            {
                "ID": message_id,
                "Subject": "Previously processed invoice",
            }
        ],
    )

    monkeypatch.setattr(
        email_ingestion.storage,
        "register_email",
        lambda message_id, subject: False,
    )

    monkeypatch.setattr(
        email_ingestion.storage,
        "should_process_email",
        lambda message_id: False,
    )

    def unexpected_download(*args, **kwargs):
        raise AssertionError(
            "A processed email should not be downloaded."
        )

    monkeypatch.setattr(
        email_ingestion,
        "get_pdf_attachments",
        unexpected_download,
    )

    results = email_ingestion.ingest_recent_invoice_emails(
        output_directory=tmp_path,
    )

    assert results == []
    assert list(tmp_path.iterdir()) == []


def test_ingestion_registers_new_email_as_pending(
    tmp_path,
    monkeypatch,
    invoice_number,
):
    """A newly discovered email should be registered."""

    message_id = "new-invoice-message"
    registration_calls = []

    monkeypatch.setattr(
        email_ingestion,
        "get_recent_emails",
        lambda start=0, limit=50: [
            {
                "ID": message_id,
                "Subject": f"Invoice - {invoice_number}",
            }
        ],
    )

    def fake_register_email(message_id, subject):
        registration_calls.append((message_id, subject))
        return True

    monkeypatch.setattr(
        email_ingestion.storage,
        "register_email",
        fake_register_email,
    )

    monkeypatch.setattr(
        email_ingestion.storage,
        "should_process_email",
        lambda message_id: True,
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_pdf_attachments",
        lambda message_id: [],
    )

    failure_calls = []

    monkeypatch.setattr(
        email_ingestion.storage,
        "mark_email_failed",
        lambda message_id, error_message: failure_calls.append(
            (message_id, error_message)
        ),
    )

    results = email_ingestion.ingest_recent_invoice_emails(
        output_directory=tmp_path,
    )

    assert registration_calls == [
        (message_id, f"Invoice - {invoice_number}")
    ]

    assert results == []

    assert failure_calls == [
        (message_id, "No PDF attachments found.")
    ]


def test_failed_email_is_retried(
    tmp_path,
    monkeypatch,
    invoice_number,
    test_db,
):
    """Previously failed emails should be eligible for another attempt."""

    message_id = "failed-invoice-message"
    part_id = "retry-invoice-part"

    messages = [
        {
            "ID": message_id,
            "Subject": f"Invoice - {invoice_number}",
        }
    ]

    registered_calls = []
    processed_checks = []
    failed_calls = []

    # Preserve the real registration function so the email record
    # is created in the temporary test database.
    original_register_email = email_ingestion.storage.register_email

    def mock_register_email(message_id, subject):
        registered_calls.append(message_id)
        return original_register_email(message_id, subject)

    monkeypatch.setattr(
        email_ingestion,
        "get_recent_emails",
        lambda start=0, limit=50: messages,
    )

    monkeypatch.setattr(
        email_ingestion.storage,
        "register_email",
        mock_register_email,
    )

    monkeypatch.setattr(
        email_ingestion.storage,
        "should_process_email",
        lambda message_id: processed_checks.append(
            message_id
        ) or True,
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_pdf_attachments",
        lambda message_id: [
            {
                "FileName": f"{invoice_number}.pdf",
                "ContentType": "application/pdf",
                "PartID": part_id,
            }
        ],
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_mailpit_api_url",
        lambda: "http://localhost:8025/api/v1",
    )

    monkeypatch.setattr(
        email_ingestion,
        "api_get",
        lambda url: b"%PDF-1.4\nRetry PDF\n%%EOF",
    )

    monkeypatch.setattr(
        email_ingestion.storage,
        "mark_email_failed",
        lambda message_id, error_message: failed_calls.append(
            (message_id, error_message)
        ),
    )

    results = email_ingestion.ingest_recent_invoice_emails(
        output_directory=tmp_path,
    )

    assert registered_calls == [message_id]
    assert processed_checks == [message_id]
    assert failed_calls == []

    assert len(results) == 1
    assert results[0]["message_id"] == message_id
    assert results[0]["downloaded_files"][0].exists()

def test_tracked_attachment_downloads_and_records_path(
    tmp_path,
    monkeypatch,
    test_db,
):
    """A new tracked PDF attachment should download and be recorded."""

    message_id = "tracked-download-message"
    part_id = "tracked-download-part"
    filename = "tracked-invoice.pdf"

    email_ingestion.storage.register_email(
        message_id,
        "Invoice submission",
    )

    pdf_content = b"%PDF-1.4\nTest invoice\n%%EOF"
    api_calls = []

    monkeypatch.setattr(
        email_ingestion,
        "get_pdf_attachments",
        lambda message_id: [
            {
                "FileName": filename,
                "ContentType": "application/pdf",
                "PartID": part_id,
            }
        ],
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_mailpit_api_url",
        lambda: "http://localhost:8025/api/v1",
    )

    monkeypatch.setattr(
        email_ingestion,
        "api_get",
        lambda url: api_calls.append(url) or pdf_content,
    )

    downloaded_files = email_ingestion.download_pdf_attachments(
        message_id=message_id,
        output_directory=tmp_path,
        use_tracking=True,
    )

    assert len(downloaded_files) == 1

    pdf_path = downloaded_files[0]

    assert pdf_path.exists()
    assert pdf_path.read_bytes() == pdf_content
    assert len(api_calls) == 1

    attachment_record = (
        email_ingestion.storage.get_email_attachment_record(
            message_id,
            part_id,
        )
    )

    assert attachment_record["filename"] == filename
    assert attachment_record["file_path"] == str(pdf_path)
    assert attachment_record["status"] == "downloaded"


def test_tracked_attachment_reuses_existing_pdf(
    tmp_path,
    monkeypatch,
    test_db,
):
    """A valid previously downloaded PDF should not be downloaded again."""

    message_id = "reuse-download-message"
    part_id = "reuse-download-part"
    filename = "reuse-invoice.pdf"

    email_ingestion.storage.register_email(
        message_id,
        "Invoice submission",
    )

    pdf_content = b"%PDF-1.4\nExisting invoice\n%%EOF"
    api_calls = []

    monkeypatch.setattr(
        email_ingestion,
        "get_pdf_attachments",
        lambda message_id: [
            {
                "FileName": filename,
                "ContentType": "application/pdf",
                "PartID": part_id,
            }
        ],
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_mailpit_api_url",
        lambda: "http://localhost:8025/api/v1",
    )

    monkeypatch.setattr(
        email_ingestion,
        "api_get",
        lambda url: api_calls.append(url) or pdf_content,
    )

    first_download = email_ingestion.download_pdf_attachments(
        message_id=message_id,
        output_directory=tmp_path,
        use_tracking=True,
    )

    second_download = email_ingestion.download_pdf_attachments(
        message_id=message_id,
        output_directory=tmp_path,
        use_tracking=True,
    )

    assert first_download == second_download
    assert first_download[0].exists()

    # The API should only have been called during the first download.
    assert len(api_calls) == 1


def test_tracked_attachment_redownloads_missing_pdf(
    tmp_path,
    monkeypatch,
    test_db,
):
    """A missing previously downloaded PDF should be downloaded again."""

    message_id = "missing-download-message"
    part_id = "missing-download-part"
    filename = "missing-invoice.pdf"

    email_ingestion.storage.register_email(
        message_id,
        "Invoice submission",
    )

    pdf_content = b"%PDF-1.4\nRecovered invoice\n%%EOF"
    api_calls = []

    monkeypatch.setattr(
        email_ingestion,
        "get_pdf_attachments",
        lambda message_id: [
            {
                "FileName": filename,
                "ContentType": "application/pdf",
                "PartID": part_id,
            }
        ],
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_mailpit_api_url",
        lambda: "http://localhost:8025/api/v1",
    )

    monkeypatch.setattr(
        email_ingestion,
        "api_get",
        lambda url: api_calls.append(url) or pdf_content,
    )

    first_download = email_ingestion.download_pdf_attachments(
        message_id=message_id,
        output_directory=tmp_path,
        use_tracking=True,
    )

    original_path = first_download[0]

    # Simulate the downloaded PDF being deleted.
    original_path.unlink()

    second_download = email_ingestion.download_pdf_attachments(
        message_id=message_id,
        output_directory=tmp_path,
        use_tracking=True,
    )

    assert len(api_calls) == 2
    assert second_download[0] == original_path
    assert original_path.exists()
    assert original_path.read_bytes() == pdf_content

    attachment_record = (
        email_ingestion.storage.get_email_attachment_record(
            message_id,
            part_id,
        )
    )

    assert attachment_record["status"] == "downloaded"
    assert attachment_record["file_path"] == str(original_path)


def test_tracked_attachment_records_failed_download(
    tmp_path,
    monkeypatch,
    test_db,
):
    """Invalid PDF content should cause the attachment to be marked failed."""

    message_id = "invalid-download-message"
    part_id = "invalid-download-part"
    filename = "invalid-invoice.pdf"

    email_ingestion.storage.register_email(
        message_id,
        "Invoice submission",
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_pdf_attachments",
        lambda message_id: [
            {
                "FileName": filename,
                "ContentType": "application/pdf",
                "PartID": part_id,
            }
        ],
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_mailpit_api_url",
        lambda: "http://localhost:8025/api/v1",
    )

    monkeypatch.setattr(
        email_ingestion,
        "api_get",
        lambda url: b"This is not a PDF file",
    )

    with pytest.raises(ValueError):
        email_ingestion.download_pdf_attachments(
            message_id=message_id,
            output_directory=tmp_path,
            use_tracking=True,
        )

    attachment_record = (
        email_ingestion.storage.get_email_attachment_record(
            message_id,
            part_id,
        )
    )

    assert attachment_record["status"] == "failed"
    assert attachment_record["error_message"] is not None

def test_recent_email_retrieval_failure_is_logged_and_propagated(
    monkeypatch,
    caplog,
):
    sensitive_error = "PRIVATE_MAILPIT_RESPONSE_DETAILS"

    def fail_to_retrieve_emails(start=0, limit=50):
        raise ConnectionError(sensitive_error)

    monkeypatch.setattr(
        email_ingestion,
        "get_recent_emails",
        fail_to_retrieve_emails,
    )

    with caplog.at_level(
        logging.ERROR,
        logger="invoice_processor",
    ):
        with pytest.raises(ConnectionError):
            email_ingestion.ingest_recent_invoice_emails()

    assert "ConnectionError" in caplog.text
    assert sensitive_error not in caplog.text

def test_email_registration_failure_does_not_stop_batch(
    tmp_path,
    monkeypatch,
    caplog,
):
    messages = [
        {"ID": "registration-failure-001", "Subject": "First email"},
        {"ID": "registration-success-002", "Subject": "Second email"},
    ]

    registration_attempts = []
    failure_calls = []

    monkeypatch.setattr(
        email_ingestion,
        "get_recent_emails",
        lambda **kwargs: messages,
    )

    def mock_register_email(message_id, subject):
        registration_attempts.append(message_id)

        if message_id == "registration-failure-001":
            raise sqlite3.OperationalError(
                "PRIVATE_DATABASE_ERROR"
            )

        return True

    monkeypatch.setattr(
        email_ingestion.storage,
        "register_email",
        mock_register_email,
    )

    monkeypatch.setattr(
        email_ingestion.storage,
        "should_process_email",
        lambda message_id: True,
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_pdf_attachments",
        lambda message_id: [],
    )

    monkeypatch.setattr(
        email_ingestion.storage,
        "mark_email_failed",
        lambda message_id, error_message, **kwargs:
            failure_calls.append(message_id),
    )

    with caplog.at_level(
        logging.ERROR,
        logger="invoice_processor",
    ):
        results = email_ingestion.ingest_recent_invoice_emails(
            output_directory=tmp_path,
        )

    assert registration_attempts == [
        "registration-failure-001",
        "registration-success-002",
    ]

    assert results == []
    assert failure_calls == ["registration-success-002"]

    assert "OperationalError" in caplog.text
    assert "PRIVATE_DATABASE_ERROR" not in caplog.text

def test_email_retry_check_failure_does_not_stop_batch(
    tmp_path,
    monkeypatch,
    caplog,
):
    messages = [
        {"ID": "retry-check-failure-001", "Subject": "First email"},
        {"ID": "retry-check-success-002", "Subject": "Second email"},
    ]

    registration_calls = []
    retry_checks = []
    failure_calls = []

    monkeypatch.setattr(
        email_ingestion,
        "get_recent_emails",
        lambda **kwargs: messages,
    )

    monkeypatch.setattr(
        email_ingestion.storage,
        "register_email",
        lambda message_id, subject:
            registration_calls.append(message_id) or True,
    )

    def mock_should_process_email(message_id):
        retry_checks.append(message_id)

        if message_id == "retry-check-failure-001":
            raise sqlite3.OperationalError(
                "PRIVATE_RETRY_CHECK_ERROR"
            )

        return True

    monkeypatch.setattr(
        email_ingestion.storage,
        "should_process_email",
        mock_should_process_email,
    )

    monkeypatch.setattr(
        email_ingestion,
        "get_pdf_attachments",
        lambda message_id: [],
    )

    monkeypatch.setattr(
        email_ingestion.storage,
        "mark_email_failed",
        lambda message_id, error_message, **kwargs:
            failure_calls.append(message_id),
    )

    with caplog.at_level(
        logging.ERROR,
        logger="invoice_processor",
    ):
        results = email_ingestion.ingest_recent_invoice_emails(
            output_directory=tmp_path,
        )

    assert registration_calls == [
        "retry-check-failure-001",
        "retry-check-success-002",
    ]

    assert retry_checks == [
        "retry-check-failure-001",
        "retry-check-success-002",
    ]

    assert results == []
    assert failure_calls == [
        "retry-check-failure-001",
        "retry-check-success-002",
    ]

    assert "OperationalError" in caplog.text
    assert "PRIVATE_RETRY_CHECK_ERROR" not in caplog.text

