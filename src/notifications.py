
import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from src.logging_config import LOGGER_NAME


logger = logging.getLogger(LOGGER_NAME)

DEFAULT_TIMEOUT = 10
SLACK_WEBHOOK_HOST = "hooks.slack.com"


def send_slack_notification(
    message: str,
    webhook_url: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> bool:
    """
    Send a notification to Slack using an Incoming Webhook.

    Args:
        message: Text content of the Slack notification.
        webhook_url: Optional webhook URL. If omitted, SLACK_WEBHOOK_URL
            is retrieved from the environment.
        timeout: Maximum HTTP request duration in seconds.

    Returns:
        True if Slack successfully accepts the notification.
        False if configuration or delivery fails.

    Raises:
        ValueError: If the message or timeout is invalid.

    Notification failures are handled without propagating exceptions
    into the invoice-processing workflow.
    """

    if not isinstance(message, str) or not message.strip():
        raise ValueError("message cannot be empty.")

    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or timeout <= 0
    ):
        raise ValueError("timeout must be greater than zero.")

    # Load environment variables from the project .env file.
    load_dotenv()

    webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        logger.warning(
            "Slack notification skipped: webhook is not configured."
        )
        return False

    # Validate the destination before sending any information.
    parsed_url = urlparse(webhook_url)

    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != SLACK_WEBHOOK_HOST
        or not parsed_url.path.startswith("/services/")
        or parsed_url.username
        or parsed_url.password
    ):
        logger.error(
            "Slack notification skipped: invalid webhook configuration."
        )
        return False

    payload = {
        "text": message,
    }

    request_body = json.dumps(payload).encode("utf-8")

    request = Request(
        url=webhook_url,
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "User-Agent": "InvoiceProcessingAutomation/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8").strip()

            if response.status == 200 and response_body == "ok":
                logger.info("Slack notification delivered successfully.")
                return True

            logger.error(
                "Slack notification rejected. HTTP status: %s.",
                response.status,
            )
            return False

    except HTTPError as error:
        logger.error(
            "Slack notification failed. HTTP status: %s.",
            error.code,
        )
        return False

    except URLError:
        logger.error(
            "Slack notification failed: connection error."
        )
        return False

    except (TimeoutError, OSError):
        logger.error(
            "Slack notification failed: request timed out or "
            "encountered a network error."
        )
        return False

    except Exception as error:
      logger.error(
          "Slack notification failed unexpectedly (%s).",
          type(error).__name__,
      )
      return False


def notify_invoice_processed() -> bool:
    """Notify Slack that an invoice was processed successfully."""

    return send_slack_notification(
        " :white_check_mark: *Invoice processed successfully*\n"
        "An invoice has been extracted, validated and saved to SQLite."
    )


def notify_invoice_validation_failed(issue_count: int) -> bool:
    """Notify Slack that an invoice failed business validation."""

    if (
        isinstance(issue_count, bool)
        or not isinstance(issue_count, int)
        or issue_count < 0
    ):
        raise ValueError("issue_count must be a non-negative integer.")

    return send_slack_notification(
        ":warning: *Invoice validation failed*\n"
        f"The invoice was rejected with {issue_count} validation issue(s)."
    )


def notify_invoice_processing_failed(
    error_type: str,
) -> bool:
    """Notify Slack about an unexpected invoice processing failure."""

    if not isinstance(error_type, str) or not error_type.strip():
        raise ValueError("error_type cannot be empty.")

    # Only send the exception class, never the exception message.
    safe_error_type = "".join(
        character
        for character in error_type
        if character.isalnum() or character == "_"
    )

    if not safe_error_type:
        raise ValueError("error_type is invalid.")

    return send_slack_notification(
        ":x: *Invoice processing failed*\n"
        f"Failure category: `{safe_error_type}`."
    )


def notify_airtable_sync_failed(
    job_id: int,
    entity_type: str,
    failure_type: str,
    retry_count: int,
    max_retries: int,
) -> bool:
    """Notify Slack about an Airtable synchronization failure."""

    if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id < 1:
        raise ValueError("job_id must be a positive integer.")

    if entity_type not in {"invoice", "quickbooks_draft"}:
        raise ValueError("Unsupported Airtable entity type.")

    if failure_type not in {"transient", "permanent"}:
        raise ValueError("Unsupported failure classification.")

    if (
        isinstance(retry_count, bool)
        or not isinstance(retry_count, int)
        or retry_count < 0
    ):
        raise ValueError("retry_count must be non-negative.")

    if (
        isinstance(max_retries, bool)
        or not isinstance(max_retries, int)
        or max_retries < 0
    ):
        raise ValueError("max_retries must be non-negative.")

    return send_slack_notification(
        ":warning: *Airtable synchronization failed*\n"
        f"Job: `{job_id}`\n"
        f"Entity: `{entity_type}`\n"
        f"Failure classification: `{failure_type}`\n"
        f"Attempts: `{retry_count}/{max_retries}`."
    )


def notify_airtable_sync_recovered(
    job_id: int,
    entity_type: str,
) -> bool:
    """Notify Slack that an Airtable synchronization recovered."""

    if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id < 1:
        raise ValueError("job_id must be a positive integer.")

    if entity_type not in {"invoice", "quickbooks_draft"}:
        raise ValueError("Unsupported Airtable entity type.")

    return send_slack_notification(
        ":white_check_mark: *Airtable synchronization recovered*\n"
        f"Job: `{job_id}`\n"
        f"Entity: `{entity_type}`\n"
        "The synchronization completed successfully after a retry."
    )
