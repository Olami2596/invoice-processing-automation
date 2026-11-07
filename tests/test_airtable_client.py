
import json
from unittest.mock import MagicMock, patch

import pytest

from src.airtable_client import (
    AirtableAPIError,
    AirtableClient,
)


@pytest.fixture
def client():
    return AirtableClient(
        pat="test_pat",
        base_id="appTest123",
        max_retries=0,
    )


def test_request_converts_timeout_to_airtable_api_error(client):
    with patch(
        "src.airtable_client.urlopen",
        side_effect=TimeoutError,
    ):
        with pytest.raises(AirtableAPIError, match="timed out"):
            client._request("GET", "https://example.com")



def test_request_rejects_json_list_response(client):
    response = MagicMock()
    response.read.return_value = json.dumps([1, 2, 3]).encode()

    context_manager = MagicMock()
    context_manager.__enter__.return_value = response

    with patch(
        "src.airtable_client.urlopen",
        return_value=context_manager,
    ):
        with pytest.raises(
            AirtableAPIError,
            match="unexpected response format",
        ):
            client._request("GET", "https://example.com")


def test_request_rejects_invalid_json(client):
    response = MagicMock()
    response.read.return_value = b"not valid json"

    context_manager = MagicMock()
    context_manager.__enter__.return_value = response

    with patch(
        "src.airtable_client.urlopen",
        return_value=context_manager,
    ):
        with pytest.raises(
            AirtableAPIError,
            match="invalid JSON",
        ):
            client._request("GET", "https://example.com")



def test_list_records_rejects_non_list_records(client):
    with patch.object(
        client,
        "_request",
        return_value={"records": "invalid"},
    ):
        with pytest.raises(
            AirtableAPIError,
            match="Unexpected Airtable records response",
        ):
            client.list_records("Invoices")


def test_list_records_rejects_invalid_record_items(client):
    with patch.object(
        client,
        "_request",
        return_value={"records": ["invalid"]},
    ):
        with pytest.raises(
            AirtableAPIError,
            match="invalid record format",
        ):
            client.list_records("Invoices")


def test_list_records_accepts_valid_records(client):
    expected_records = [
        {"id": "rec123", "fields": {"Invoice Number": "INV-TEST-001"}}
    ]

    with patch.object(
        client,
        "_request",
        return_value={"records": expected_records},
    ):
        records = client.list_records("Invoices")

    assert records == expected_records


def test_create_record_serializes_payload_as_json_bytes(client):
    fields = {
        "Invoice Number": "INV-TEST-001",
        "Total Amount": 854625.00,
    }

    response = MagicMock()
    response.read.return_value = json.dumps({
        "id": "rec123",
        "fields": fields,
    }).encode("utf-8")

    context_manager = MagicMock()
    context_manager.__enter__.return_value = response

    with patch(
        "src.airtable_client.urlopen",
        return_value=context_manager,
    ) as mock_urlopen:

        result = client.create_record("Invoices", fields)

    assert result["id"] == "rec123"

    request = mock_urlopen.call_args.args[0]

    assert request.get_method() == "POST"
    assert json.loads(request.data.decode("utf-8")) == {
        "fields": fields,
    }


def test_update_record_serializes_payload_as_json_bytes(client):
    fields = {
        "Invoice Number": "INV-TEST-001",
        "Total Amount": 854625.00,
    }

    response = MagicMock()
    response.read.return_value = json.dumps({
        "id": "rec123",
        "fields": fields,
    }).encode("utf-8")

    context_manager = MagicMock()
    context_manager.__enter__.return_value = response

    with patch(
        "src.airtable_client.urlopen",
        return_value=context_manager,
    ) as mock_urlopen:

        result = client.update_record(
            table_name="Invoices",
            record_id="rec123",
            fields=fields,
        )

    assert result["id"] == "rec123"

    request = mock_urlopen.call_args.args[0]

    assert request.get_method() == "PATCH"
    assert json.loads(request.data.decode("utf-8")) == {
        "fields": fields,
    }
