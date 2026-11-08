
import json
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import pytest

from src.notifications import send_slack_notification


TEST_WEBHOOK_URL = (
    "https://hooks.slack.com/services/TEST/WEBHOOK/TOKEN"
)


def test_send_slack_notification_success():
    """A successful Slack response should return True."""

    response = Mock()
    response.status = 200
    response.read.return_value = b"ok"
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    with patch(
        "src.notifications.urlopen",
        return_value=response,
    ) as mock_urlopen:

        result = send_slack_notification(
            "Test notification",
            webhook_url=TEST_WEBHOOK_URL,
        )

    assert result is True
    mock_urlopen.assert_called_once()

    request = mock_urlopen.call_args.args[0]

    assert request.full_url == TEST_WEBHOOK_URL
    assert request.get_method() == "POST"
    assert json.loads(request.data.decode("utf-8")) == {
        "text": "Test notification"
    }


def test_send_slack_notification_missing_webhook(monkeypatch):
    """Missing webhook configuration should return False."""

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")

    result = send_slack_notification("Test notification")

    assert result is False


def test_send_slack_notification_invalid_webhook():
    """An invalid webhook URL should not be contacted."""

    with patch("src.notifications.urlopen") as mock_urlopen:
        result = send_slack_notification(
            "Test notification",
            webhook_url="https://example.com/webhook",
        )

    assert result is False
    mock_urlopen.assert_not_called()


def test_send_slack_notification_http_error():
    """An HTTP error should return False without escaping."""

    error = HTTPError(
        TEST_WEBHOOK_URL,
        500,
        "Internal Server Error",
        None,
        BytesIO(b"Internal Server Error"),
    )

    with patch(
        "src.notifications.urlopen",
        side_effect=error,
    ):
        result = send_slack_notification(
            "Test notification",
            webhook_url=TEST_WEBHOOK_URL,
        )

    assert result is False


def test_send_slack_notification_connection_error():
    """A connection error should return False."""

    with patch(
        "src.notifications.urlopen",
        side_effect=URLError("Connection refused"),
    ):
        result = send_slack_notification(
            "Test notification",
            webhook_url=TEST_WEBHOOK_URL,
        )

    assert result is False


def test_send_slack_notification_timeout():
    """A timeout should return False."""

    with patch(
        "src.notifications.urlopen",
        side_effect=TimeoutError("Request timed out"),
    ):
        result = send_slack_notification(
            "Test notification",
            webhook_url=TEST_WEBHOOK_URL,
        )

    assert result is False


def test_send_slack_notification_unexpected_response():
    """An unexpected Slack response should return False."""

    response = Mock()
    response.status = 200
    response.read.return_value = b"unexpected response"
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    with patch(
        "src.notifications.urlopen",
        return_value=response,
    ):
        result = send_slack_notification(
            "Test notification",
            webhook_url=TEST_WEBHOOK_URL,
        )

    assert result is False


@pytest.mark.parametrize(
    "message",
    ["", " ", None, 123],
)
def test_send_slack_notification_rejects_invalid_message(message):
    """Empty or non-string messages should raise ValueError."""

    with pytest.raises(ValueError):
        send_slack_notification(
            message,
            webhook_url=TEST_WEBHOOK_URL,
        )


@pytest.mark.parametrize(
    "timeout",
    [0, -1, True, "10"],
)
def test_send_slack_notification_rejects_invalid_timeout(timeout):
    """Invalid timeout values should raise ValueError."""

    with pytest.raises(ValueError):
        send_slack_notification(
            "Test notification",
            webhook_url=TEST_WEBHOOK_URL,
            timeout=timeout,
        )


def test_notify_invoice_processed(monkeypatch):
    """Successful invoice processing should generate a notification."""

    from src import notifications

    sender = Mock(return_value=True)

    monkeypatch.setattr(
        notifications,
        "send_slack_notification",
        sender,
    )

    assert notifications.notify_invoice_processed() is True

    sender.assert_called_once()
    assert "Invoice processed successfully" in sender.call_args.args[0]


def test_notify_invoice_validation_failed(monkeypatch):
    from src import notifications

    sender = Mock(return_value=True)

    monkeypatch.setattr(
        notifications,
        "send_slack_notification",
        sender,
    )

    assert notifications.notify_invoice_validation_failed(2) is True

    assert "2 validation issue(s)" in sender.call_args.args[0]


def test_notify_invoice_processing_failed(monkeypatch):
    from src import notifications

    sender = Mock(return_value=True)

    monkeypatch.setattr(
        notifications,
        "send_slack_notification",
        sender,
    )

    assert notifications.notify_invoice_processing_failed(
        "RuntimeError"
    ) is True

    assert "RuntimeError" in sender.call_args.args[0]


def test_notify_airtable_sync_failed(monkeypatch):
    from src import notifications

    sender = Mock(return_value=True)

    monkeypatch.setattr(
        notifications,
        "send_slack_notification",
        sender,
    )

    result = notifications.notify_airtable_sync_failed(
        job_id=12,
        entity_type="invoice",
        failure_type="transient",
        retry_count=2,
        max_retries=5,
    )

    assert result is True

    message = sender.call_args.args[0]

    assert "Airtable synchronization failed" in message
    assert "12" in message
    assert "2/5" in message


def test_notify_airtable_sync_recovered(monkeypatch):
    from src import notifications

    sender = Mock(return_value=True)

    monkeypatch.setattr(
        notifications,
        "send_slack_notification",
        sender,
    )

    result = notifications.notify_airtable_sync_recovered(
        job_id=12,
        entity_type="invoice",
    )

    assert result is True

    assert "Airtable synchronization recovered" in (
        sender.call_args.args[0]
    )


def test_notify_invoice_validation_failed_rejects_negative_count():
    from src.notifications import notify_invoice_validation_failed

    with pytest.raises(ValueError):
        notify_invoice_validation_failed(-1)


def test_notify_invoice_processing_failed_does_not_include_raw_message(
    monkeypatch,
):
    from src import notifications

    sender = Mock(return_value=True)

    monkeypatch.setattr(
        notifications,
        "send_slack_notification",
        sender,
    )

    notifications.notify_invoice_processing_failed(
        "RuntimeError: Sensitive customer information"
    )

    message = sender.call_args.args[0]

    assert "RuntimeError" in message
    assert "Sensitive customer information" not in message
