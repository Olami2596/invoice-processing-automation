import pytest

from src import airtable_worker
from src.airtable_worker import classify_airtable_failure
from src.airtable_client import (
    AirtableAPIError,
    AirtableAuthenticationError,
    AirtablePermissionError,
    AirtableNotFoundError,
    AirtableRateLimitError,
)


import pytest


@pytest.mark.parametrize(
    "exception",
    [
        AirtableAuthenticationError("Authentication failed", 401),
        AirtablePermissionError("Permission denied", 403),
        AirtableNotFoundError("Resource not found", 404),
        ValueError("Invalid data"),
        LookupError("Local record missing"),
    ],
)
def test_classify_permanent_airtable_failures(exception):
    assert classify_airtable_failure(exception) == "permanent"


@pytest.mark.parametrize(
    "exception",
    [
        AirtableRateLimitError("Rate limit", 429),
        AirtableAPIError("Server error", 500),
        AirtableAPIError("Service unavailable", 503),
        AirtableAPIError("Network error"),
        TimeoutError("Request timed out"),
    ],
)
def test_classify_transient_airtable_failures(exception):
    assert classify_airtable_failure(exception) == "transient"


def test_classify_public_api_billing_limit_as_permanent():
    exception = AirtableRateLimitError(
        "Billing limit exceeded",
        429,
        "PUBLIC_API_BILLING_LIMIT_EXCEEDED",
    )

    assert classify_airtable_failure(exception) == "permanent"


def test_classify_unknown_exception_as_transient():
    exception = RuntimeError("Unexpected error")

    assert classify_airtable_failure(exception) == "transient"


def test_process_airtable_sync_job_successful_invoice(monkeypatch):
    job = {
        "id": 1,
        "entity_type": "invoice",
        "local_record_id": 10,
        "status": "pending",
        "retry_count": 0,
    }

    invoice = object()
    source_file = "invoice.pdf"
    client = object()
    synced = {}

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        lambda job_id: job,
    )

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_invoice_by_id",
        lambda invoice_id: (invoice, source_file),
    )

    def mock_sync(**kwargs):
        assert kwargs["client"] is client
        assert kwargs["invoice"] is invoice
        assert kwargs["source_file"] == source_file
        assert kwargs["sqlite_invoice_id"] == 10
        return {"id": "recINVOICE123"}

    monkeypatch.setattr(
        airtable_worker,
        "sync_invoice_to_airtable",
        mock_sync,
    )

    def mock_mark_synced(**kwargs):
        synced.update(kwargs)

    monkeypatch.setattr(
        airtable_worker.storage,
        "mark_airtable_sync_synced",
        mock_mark_synced,
    )

    result = airtable_worker.process_airtable_sync_job(
        job_id=1,
        client=client,
    )

    assert result is True
    assert synced == {
        "job_id": 1,
        "airtable_record_id": "recINVOICE123",
    }


def test_process_airtable_sync_job_successful_draft(monkeypatch):
    job = {
        "id": 2,
        "entity_type": "quickbooks_draft",
        "local_record_id": 20,
        "status": "pending",
        "retry_count": 0,
    }

    draft = object()
    client = object()
    synced = {}

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        lambda job_id: job,
    )

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_quickbooks_draft_by_id",
        lambda draft_id: draft,
    )

    def mock_sync(**kwargs):
        assert kwargs["client"] is client
        assert kwargs["draft"] is draft
        assert kwargs["sqlite_draft_id"] == 20
        return {"id": "recDRAFT123"}

    monkeypatch.setattr(
        airtable_worker,
        "sync_quickbooks_draft_to_airtable",
        mock_sync,
    )

    monkeypatch.setattr(
        airtable_worker.storage,
        "mark_airtable_sync_synced",
        lambda **kwargs: synced.update(kwargs),
    )

    result = airtable_worker.process_airtable_sync_job(
        job_id=2,
        client=client,
    )

    assert result is True
    assert synced["airtable_record_id"] == "recDRAFT123"


def test_process_airtable_sync_job_not_found(monkeypatch):
    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        lambda job_id: None,
    )

    with pytest.raises(LookupError):
        airtable_worker.process_airtable_sync_job(
            job_id=999,
            client=object(),
        )


def test_process_airtable_sync_job_skips_non_pending(monkeypatch):
    job = {
        "id": 3,
        "entity_type": "invoice",
        "local_record_id": 30,
        "status": "synced",
        "retry_count": 0,
    }

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        lambda job_id: job,
    )

    result = airtable_worker.process_airtable_sync_job(
        job_id=3,
        client=object(),
    )

    assert result is False


def test_process_airtable_sync_job_skips_exhausted_retries(monkeypatch):
    job = {
        "id": 4,
        "entity_type": "invoice",
        "local_record_id": 40,
        "status": "pending",
        "retry_count": airtable_worker.MAX_AIRTABLE_RETRIES,
    }

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        lambda job_id: job,
    )

    result = airtable_worker.process_airtable_sync_job(
        job_id=4,
        client=object(),
    )

    assert result is False


def test_process_airtable_sync_job_missing_invoice(monkeypatch):
    job = {
        "id": 5,
        "entity_type": "invoice",
        "local_record_id": 50,
        "status": "pending",
        "retry_count": 0,
    }

    failures = {}

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        lambda job_id: job,
    )

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_invoice_by_id",
        lambda invoice_id: None,
    )

    monkeypatch.setattr(
        airtable_worker.storage,
        "mark_airtable_sync_failed",
        lambda **kwargs: failures.update(kwargs),
    )

    result = airtable_worker.process_airtable_sync_job(
        job_id=5,
        client=object(),
    )

    assert result is False
    assert failures["job_id"] == 5
    assert "LookupError" in failures["error_message"]


def test_process_airtable_sync_job_handles_airtable_failure(monkeypatch):
    job = {
        "id": 6,
        "entity_type": "invoice",
        "local_record_id": 60,
        "status": "pending",
        "retry_count": 0,
    }

    invoice = object()
    failures = {}

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        lambda job_id: job,
    )

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_invoice_by_id",
        lambda invoice_id: (invoice, "invoice.pdf"),
    )

    def mock_sync(**kwargs):
        raise RuntimeError("Sensitive invoice details must not be logged")

    monkeypatch.setattr(
        airtable_worker,
        "sync_invoice_to_airtable",
        mock_sync,
    )

    monkeypatch.setattr(
        airtable_worker.storage,
        "mark_airtable_sync_failed",
        lambda **kwargs: failures.update(kwargs),
    )

    result = airtable_worker.process_airtable_sync_job(
        job_id=6,
        client=object(),
    )

    assert result is False
    assert failures["job_id"] == 6
    assert failures["error_message"] == (
        "Airtable synchronization failed (RuntimeError)."
    )
    assert "Sensitive invoice details" not in failures["error_message"]


def test_process_pending_airtable_sync_jobs_empty_queue(monkeypatch):
    monkeypatch.setattr(
        airtable_worker.storage,
        "get_pending_airtable_sync_jobs",
        lambda limit: [],
    )

    result = airtable_worker.process_pending_airtable_sync_jobs(client=object())

    assert result == {
        "total": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
    }


def test_process_pending_airtable_sync_jobs_success(monkeypatch):
    jobs = [
        {"id": 1},
        {"id": 2},
        {"id": 3},
    ]

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_pending_airtable_sync_jobs",
        lambda limit: jobs,
    )

    def mock_process(job_id, client):
        return True

    monkeypatch.setattr(
        airtable_worker,
        "process_airtable_sync_job",
        mock_process,
    )

    result = airtable_worker.process_pending_airtable_sync_jobs(client=object())

    assert result == {
        "total": 3,
        "succeeded": 3,
        "failed": 0,
        "skipped": 0,
    }


def test_process_pending_airtable_sync_jobs_continues_after_error(
    monkeypatch,
):
    jobs = [
        {"id": 1},
        {"id": 2},
        {"id": 3},
    ]

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_pending_airtable_sync_jobs",
        lambda limit: jobs,
    )

    processed_jobs = []

    def mock_process(job_id, client):
        processed_jobs.append(job_id)

        if job_id == 2:
            raise RuntimeError("Unexpected error")

        return True

    monkeypatch.setattr(
        airtable_worker,
        "process_airtable_sync_job",
        mock_process,
    )

    result = airtable_worker.process_pending_airtable_sync_jobs(client=object())

    assert processed_jobs == [1, 2, 3]

    assert result == {
        "total": 3,
        "succeeded": 2,
        "failed": 1,
        "skipped": 0,
    }


def test_process_pending_airtable_sync_jobs_counts_skipped(
    monkeypatch,
):
    jobs = [
        {"id": 1},
        {"id": 2},
    ]

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_pending_airtable_sync_jobs",
        lambda limit: jobs,
    )

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        lambda job_id: {
            "id": job_id,
            "status": "pending",
        },
    )

    def mock_process(job_id, client):
        return job_id == 1

    monkeypatch.setattr(
        airtable_worker,
        "process_airtable_sync_job",
        mock_process,
    )

    result = airtable_worker.process_pending_airtable_sync_jobs(client=object())

    assert result == {
        "total": 2,
        "succeeded": 1,
        "failed": 0,
        "skipped": 1,
    }


def test_process_pending_airtable_sync_jobs_counts_failures(
    monkeypatch,
):
    jobs = [
        {"id": 1},
        {"id": 2},
    ]

    job_statuses = {
        1: "failed",
        2: "pending",
    }

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_pending_airtable_sync_jobs",
        lambda limit: jobs,
    )

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        lambda job_id: {
            "id": job_id,
            "status": job_statuses[job_id],
        },
    )

    def mock_process(job_id, client):
        return False

    monkeypatch.setattr(
        airtable_worker,
        "process_airtable_sync_job",
        mock_process,
    )

    result = airtable_worker.process_pending_airtable_sync_jobs(client=object())

    assert result == {
        "total": 2,
        "succeeded": 0,
        "failed": 1,
        "skipped": 1,
    }
