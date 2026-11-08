
from unittest.mock import Mock

import pytest

from src import airtable_worker


@pytest.fixture
def worker_mocks(monkeypatch):
    """Mock storage, Airtable sync operations, and Slack notifications."""

    job = {
        "id": 101,
        "entity_type": "invoice",
        "local_record_id": 1,
        "status": "pending",
        "retry_count": 0,
        "manual_retry": 0,
    }

    mocks = {
        "get_job": Mock(return_value=job.copy()),
        "claim_job": Mock(return_value="test-claim-token"),
        "mark_failed": Mock(),
        "mark_synced": Mock(),
        "get_invoice": Mock(return_value=({"invoice_number": "TEST-101"}, "test.pdf")),
        "sync_invoice": Mock(return_value={"id": "recABC123"}),
        "notify_failed": Mock(return_value=True),
        "notify_recovered": Mock(return_value=True),
    }

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        mocks["get_job"],
    )
    monkeypatch.setattr(
        airtable_worker.storage,
        "claim_airtable_sync_job",
        mocks["claim_job"],
    )
    monkeypatch.setattr(
        airtable_worker.storage,
        "mark_airtable_sync_failed",
        mocks["mark_failed"],
    )
    monkeypatch.setattr(
        airtable_worker.storage,
        "mark_airtable_sync_synced",
        mocks["mark_synced"],
    )
    monkeypatch.setattr(
        airtable_worker.storage,
        "get_invoice_by_id",
        mocks["get_invoice"],
    )
    monkeypatch.setattr(
        airtable_worker,
        "sync_invoice_to_airtable",
        mocks["sync_invoice"],
    )
    monkeypatch.setattr(
        airtable_worker,
        "notify_airtable_sync_failed",
        mocks["notify_failed"],
    )
    monkeypatch.setattr(
        airtable_worker,
        "notify_airtable_sync_recovered",
        mocks["notify_recovered"],
    )

    return mocks


def test_permanent_failure_sends_notification(
    worker_mocks,
    monkeypatch,
):
    """Permanent failures should trigger an immediate notification."""

    monkeypatch.setattr(
        airtable_worker,
        "AirtableClient",
        Mock(),
    )

    worker_mocks["get_job"].side_effect = [
        {
            "id": 101,
            "entity_type": "invoice",
            "local_record_id": 1,
            "status": "pending",
            "retry_count": 0,
            "manual_retry": 0,
        },
        {
            "id": 101,
            "entity_type": "invoice",
            "local_record_id": 1,
            "status": "failed",
            "retry_count": 1,
            "manual_retry": 0,
        },
    ]

    worker_mocks["get_invoice"].return_value = None

    result = airtable_worker.process_airtable_sync_job(101)

    assert result is False

    worker_mocks["mark_failed"].assert_called_once()
    worker_mocks["notify_failed"].assert_called_once_with(
        job_id=101,
        entity_type="invoice",
        failure_type="permanent",
        retry_count=1,
        max_retries=airtable_worker.MAX_AIRTABLE_RETRIES,
    )


def test_transient_failure_does_not_send_premature_notification(
    worker_mocks,
    monkeypatch,
):
    """Transient failures should not notify while retries remain."""

    monkeypatch.setattr(
        airtable_worker,
        "AirtableClient",
        Mock(),
    )

    worker_mocks["sync_invoice"].side_effect = TimeoutError(
        "Simulated Airtable timeout"
    )

    worker_mocks["get_job"].side_effect = [
        {
            "id": 101,
            "entity_type": "invoice",
            "local_record_id": 1,
            "status": "pending",
            "retry_count": 0,
            "manual_retry": 0,
        },
        {
            "id": 101,
            "entity_type": "invoice",
            "local_record_id": 1,
            "status": "failed",
            "retry_count": 1,
            "manual_retry": 0,
        },
    ]

    result = airtable_worker.process_airtable_sync_job(101)

    assert result is False

    worker_mocks["mark_failed"].assert_called_once()
    worker_mocks["notify_failed"].assert_not_called()


def test_exhausted_retries_send_notification(
    worker_mocks,
    monkeypatch,
):
    """The final transient failure should trigger a notification."""

    monkeypatch.setattr(
        airtable_worker,
        "AirtableClient",
        Mock(),
    )

    worker_mocks["sync_invoice"].side_effect = TimeoutError(
        "Simulated Airtable timeout"
    )

    worker_mocks["get_job"].side_effect = [
        {
            "id": 101,
            "entity_type": "invoice",
            "local_record_id": 1,
            "status": "pending",
            "retry_count": airtable_worker.MAX_AIRTABLE_RETRIES - 1,
            "manual_retry": 0,
        },
        {
            "id": 101,
            "entity_type": "invoice",
            "local_record_id": 1,
            "status": "failed",
            "retry_count": airtable_worker.MAX_AIRTABLE_RETRIES,
            "manual_retry": 0,
        },
    ]

    result = airtable_worker.process_airtable_sync_job(101)

    assert result is False

    worker_mocks["mark_failed"].assert_called_once()
    worker_mocks["notify_failed"].assert_called_once_with(
        job_id=101,
        entity_type="invoice",
        failure_type="transient",
        retry_count=airtable_worker.MAX_AIRTABLE_RETRIES,
        max_retries=airtable_worker.MAX_AIRTABLE_RETRIES,
    )


def test_successful_retry_sends_recovery_notification(
    worker_mocks,
    monkeypatch,
):
    """A previously failed job should trigger a recovery notification."""

    monkeypatch.setattr(
        airtable_worker,
        "AirtableClient",
        Mock(),
    )

    worker_mocks["get_job"].return_value = {
        "id": 101,
        "entity_type": "invoice",
        "local_record_id": 1,
        "status": "pending",
        "retry_count": 2,
        "manual_retry": 0,
    }

    result = airtable_worker.process_airtable_sync_job(101)

    assert result is True

    worker_mocks["mark_synced"].assert_called_once_with(
        job_id=101,
        airtable_record_id="recABC123",
        claim_token="test-claim-token",
    )

    worker_mocks["notify_recovered"].assert_called_once_with(
        job_id=101,
        entity_type="invoice",
    )

    worker_mocks["notify_failed"].assert_not_called()
