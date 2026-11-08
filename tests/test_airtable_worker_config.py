
from unittest.mock import Mock

import pytest

from src import airtable_worker
from src.airtable_sync import AirtableSyncConfigurationError

@pytest.fixture(autouse=True)
def disable_real_slack_notifications(monkeypatch):
    """Prevent configuration tests from sending real Slack messages."""

    monkeypatch.setattr(
        airtable_worker,
        "notify_airtable_sync_failed",
        Mock(return_value=True),
    )

    monkeypatch.setattr(
        airtable_worker,
        "notify_airtable_sync_recovered",
        Mock(return_value=True),
    )

def test_configuration_error_is_permanent():
    exc = AirtableSyncConfigurationError(
        "Missing Airtable table configuration."
    )

    assert airtable_worker.classify_airtable_failure(exc) == "permanent"


def test_airtable_client_value_error_is_permanent():
    exc = ValueError("Missing Airtable credentials.")

    assert airtable_worker.classify_airtable_failure(exc) == "permanent"


def test_unexpected_error_is_transient():
    exc = RuntimeError("Temporary unexpected failure.")

    assert airtable_worker.classify_airtable_failure(exc) == "transient"



def test_configuration_error_marks_job_as_permanently_failed(
    monkeypatch,
):
    job = {
        "id": 10,
        "status": "pending",
        "retry_count": 0,
        "manual_retry": 0,
        "entity_type": "invoice",
        "local_record_id": 1,
    }

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        lambda job_id: job,
    )

    monkeypatch.setattr(
        airtable_worker.storage,
        "claim_airtable_sync_job",
        lambda job_id: "test-claim-token",
    )

    monkeypatch.setattr(
        airtable_worker,
        "AirtableClient",
        Mock(
            side_effect=AirtableSyncConfigurationError(
                "Missing Airtable table configuration."
            )
        ),
    )

    mark_failed = Mock()

    monkeypatch.setattr(
        airtable_worker.storage,
        "mark_airtable_sync_failed",
        mark_failed,
    )

    result = airtable_worker.process_airtable_sync_job(job_id=10)

    assert result is False

    mark_failed.assert_called_once_with(
        job_id=10,
        error_message=(
            "Airtable synchronization failed "
            "(AirtableSyncConfigurationError)."
        ),
        claim_token="test-claim-token",
        failure_type="permanent",
    )



def test_client_initialization_error_does_not_escape_worker(
    monkeypatch,
):
    job = {
        "id": 11,
        "status": "pending",
        "retry_count": 0,
        "manual_retry": 0,
        "entity_type": "invoice",
        "local_record_id": 1,
    }

    monkeypatch.setattr(
        airtable_worker.storage,
        "get_airtable_sync_job",
        lambda job_id: job,
    )

    monkeypatch.setattr(
        airtable_worker.storage,
        "claim_airtable_sync_job",
        lambda job_id: "test-claim-token",
    )

    monkeypatch.setattr(
        airtable_worker,
        "AirtableClient",
        Mock(side_effect=ValueError("Missing Airtable credentials.")),
    )

    mark_failed = Mock()

    monkeypatch.setattr(
        airtable_worker.storage,
        "mark_airtable_sync_failed",
        mark_failed,
    )

    result = airtable_worker.process_airtable_sync_job(job_id=11)

    assert result is False

    mark_failed.assert_called_once_with(
        job_id=11,
        error_message=(
            "Airtable synchronization failed (ValueError)."
        ),
        claim_token="test-claim-token",
        failure_type="permanent",
    )
