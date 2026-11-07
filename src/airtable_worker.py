
import logging

from src.airtable_client import (
    AirtableClient,
    AirtableAPIError,
    AirtableAuthenticationError,
    AirtablePermissionError,
    AirtableNotFoundError,
    AirtableRateLimitError,
)
from src.airtable_sync import (
    AirtableSyncConfigurationError,
    sync_invoice_to_airtable,
    sync_quickbooks_draft_to_airtable,
)
from src import storage
from src.storage import MAX_AIRTABLE_RETRIES
from src.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


def classify_airtable_failure(exc: Exception) -> str:
    """Classify an Airtable synchronization failure."""

    permanent_errors = (
        AirtableAuthenticationError,
        AirtablePermissionError,
        AirtableNotFoundError,
        AirtableSyncConfigurationError,
        ValueError,
        LookupError,
    )

    if isinstance(exc, permanent_errors):
        return "permanent"

    if isinstance(exc, AirtableRateLimitError):
        if exc.error_type == "PUBLIC_API_BILLING_LIMIT_EXCEEDED":
            return "permanent"
        return "transient"

    if isinstance(exc, AirtableAPIError):
        if exc.status_code is not None:
            if exc.status_code in (408, 425) or exc.status_code >= 500:
                return "transient"
            if 400 <= exc.status_code < 500:
                return "permanent"
        return "transient"

    return "transient"


def process_airtable_sync_job(
    job_id: int,
    client: AirtableClient | None = None,
) -> bool:
    """Process one pending Airtable synchronization job."""

    job = storage.get_airtable_sync_job(job_id)

    if job is None:
        raise LookupError(f"Airtable sync job {job_id} does not exist.")

    if job["status"] != "pending":
        logger.info("Airtable sync job skipped because it is not pending.")
        return False

    if (
        job["retry_count"] >= MAX_AIRTABLE_RETRIES
        and not job.get("manual_retry", 0)
    ):
        logger.warning(
            "Airtable sync job skipped because retry limit is exhausted."
        )
        return False

    try:
        # Client initialization is deliberately inside the try block.
        # Configuration and connection errors must be recorded against
        # the job rather than crashing the worker.
        if client is None:
            client = AirtableClient()

        entity_type = job["entity_type"]
        local_record_id = job["local_record_id"]

        if entity_type == "invoice":
            result = storage.get_invoice_by_id(local_record_id)

            if result is None:
                raise LookupError("Local invoice record not found.")

            invoice, source_file = result

            airtable_record = sync_invoice_to_airtable(
                client=client,
                invoice=invoice,
                source_file=source_file,
                sqlite_invoice_id=local_record_id,
            )

        elif entity_type == "quickbooks_draft":
            draft = storage.get_quickbooks_draft_by_id(local_record_id)

            if draft is None:
                raise LookupError("Local QuickBooks draft not found.")

            airtable_record = sync_quickbooks_draft_to_airtable(
                client=client,
                draft=draft,
                sqlite_draft_id=local_record_id,
            )

        else:
            raise ValueError("Unsupported Airtable sync entity type.")

        if not isinstance(airtable_record, dict):
            raise ValueError("Airtable response is not a valid record object.")

        airtable_record_id = airtable_record.get("id")

        if (
            not isinstance(airtable_record_id, str)
            or not airtable_record_id.strip()
        ):
            raise ValueError(
                "Airtable response does not contain a valid record ID."
            )

        storage.mark_airtable_sync_synced(
            job_id=job_id,
            airtable_record_id=airtable_record_id,
        )

        logger.info("Airtable sync job completed successfully.")
        return True

    except Exception as exc:
        failure_type = classify_airtable_failure(exc)

        logger.error(
            "Airtable sync job failed. "
            "Exception type: %s, "
            "HTTP status: %s, "
            "Airtable error type: %s, "
            "failure classification: %s.",
            type(exc).__name__,
            getattr(exc, "status_code", None),
            getattr(exc, "error_type", None),
            failure_type,
        )

        storage.mark_airtable_sync_failed(
            job_id=job_id,
            error_message=(
                f"Airtable synchronization failed ({type(exc).__name__})."
            ),
            failure_type=failure_type,
        )

        return False


def process_pending_airtable_sync_jobs(
    limit: int = 100,
    client: AirtableClient | None = None,
) -> dict:
    """Promote due retries and process pending Airtable synchronization jobs."""

    if limit <= 0:
        raise ValueError("limit must be greater than zero.")

    promoted = storage.promote_due_airtable_sync_retries(limit=limit)

    if promoted:
        logger.info(
            "Promoted %s Airtable synchronization jobs for retry.",
            promoted,
        )

    jobs = storage.get_pending_airtable_sync_jobs(limit=limit)

    summary = {
        "total": len(jobs),
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
    }

    if not jobs:
        logger.info("No pending Airtable sync jobs found.")
        return summary

    for job in jobs:
        job_id = job["id"]

        try:
            success = process_airtable_sync_job(
                job_id=job_id,
                client=client,
            )

            if success:
                summary["succeeded"] += 1
            else:
                updated_job = storage.get_airtable_sync_job(job_id)

                if updated_job and updated_job["status"] == "failed":
                    summary["failed"] += 1
                else:
                    summary["skipped"] += 1

        except Exception as exc:
            logger.error(
                "Unexpected Airtable worker error. Exception type: %s",
                type(exc).__name__,
            )
            summary["failed"] += 1

    logger.info(
        "Airtable batch completed. Total: %s, succeeded: %s, "
        "failed: %s, skipped: %s",
        summary["total"],
        summary["succeeded"],
        summary["failed"],
        summary["skipped"],
    )

    return summary
