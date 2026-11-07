import sqlite3
from urllib.error import HTTPError, URLError
import pytest
from src import pipeline, storage


# ---------------------------------------------------------
# Tests for classify_failure()
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "error, expected",
    [
        (TimeoutError("Request timed out"), "transient"),
        (ConnectionError("Connection lost"), "transient"),
        (URLError("Network unavailable"), "transient"),
        (FileNotFoundError("Invoice not found"), "permanent"),
        (PermissionError("Permission denied"), "permanent"),
        (
            sqlite3.IntegrityError("Duplicate invoice"),
            "permanent",
        ),
        (
            sqlite3.OperationalError("Database temporarily locked"),
            "transient",
        ),
        (ValueError("Unexpected input"), "transient"),
        (RuntimeError("Unexpected processing error"), "transient"),
    ],
)
def test_classify_failure(error, expected):
    assert pipeline.classify_failure(error) == expected


@pytest.mark.parametrize(
    "status_code, expected",
    [
        (408, "transient"),
        (425, "transient"),
        (429, "transient"),
        (500, "transient"),
        (502, "transient"),
        (503, "transient"),
        (504, "transient"),
        (400, "permanent"),
        (401, "permanent"),
        (403, "permanent"),
        (404, "permanent"),
    ],
)
def test_classify_http_errors(status_code, expected):
    error = HTTPError(
        url="https://example.com",
        code=status_code,
        msg="Test HTTP error",
        hdrs=None,
        fp=None,
    )

    assert pipeline.classify_failure(error) == expected


# ---------------------------------------------------------
# Tests for classify_email_failure()
# ---------------------------------------------------------

def test_email_with_pending_attachment_is_transient():
    records = [
        {
            "status": "pending",
            "retry_count": 0,
            "failure_type": None,
        }
    ]

    assert pipeline.classify_email_failure(records) == "transient"


def test_email_with_downloaded_attachment_is_transient():
    records = [
        {
            "status": "downloaded",
            "retry_count": 0,
            "failure_type": None,
        }
    ]

    assert pipeline.classify_email_failure(records) == "transient"


def test_email_with_processed_attachment_is_not_failed():
    records = [
        {
            "status": "processed",
            "retry_count": 0,
            "failure_type": None,
        }
    ]

    # No remaining failed or unprocessed attachment.
    assert pipeline.classify_email_failure(records) == "permanent"


def test_email_with_retryable_transient_failure_is_transient():
    records = [
        {
            "status": "failed",
            "retry_count": 1,
            "failure_type": "transient",
        }
    ]

    assert pipeline.classify_email_failure(records) == "transient"


def test_email_with_permanent_attachment_failure_is_permanent():
    records = [
        {
            "status": "failed",
            "retry_count": 1,
            "failure_type": "permanent",
        }
    ]

    assert pipeline.classify_email_failure(records) == "permanent"


def test_email_with_exhausted_transient_retries_is_permanent():
    records = [
        {
            "status": "failed",
            "retry_count": storage.MAX_RETRIES,
            "failure_type": "transient",
        }
    ]

    assert pipeline.classify_email_failure(records) == "permanent"


def test_email_with_mixed_processed_and_retryable_attachments_is_transient():
    records = [
        {
            "status": "processed",
            "retry_count": 0,
            "failure_type": None,
        },
        {
            "status": "failed",
            "retry_count": 1,
            "failure_type": "transient",
        },
    ]

    assert pipeline.classify_email_failure(records) == "transient"
