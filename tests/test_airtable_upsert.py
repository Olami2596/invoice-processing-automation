from unittest.mock import Mock

import pytest

from src.airtable_sync import (
    AirtableDuplicateRecordError,
    upsert_record_by_sqlite_id,
)


@pytest.fixture
def client():
    return Mock()


def test_upsert_creates_record_when_no_match_exists(client):
    client.list_records.return_value = []
    client.create_record.return_value = {
        "id": "rec123",
        "fields": {"Invoice Number": "INV-001"},
    }

    result = upsert_record_by_sqlite_id(
        client=client,
        table_name="Invoices",
        sqlite_id_field="SQLite Invoice ID",
        sqlite_id=10,
        fields={"Invoice Number": "INV-001"},
    )

    assert result["id"] == "rec123"

    client.list_records.assert_called_once_with(
        table_name="Invoices",
        page_size=100,
        max_records=2,
        filter_by_formula="{SQLite Invoice ID}=10",
    )

    client.create_record.assert_called_once_with(
        table_name="Invoices",
        fields={"Invoice Number": "INV-001"},
    )

    client.update_record.assert_not_called()


def test_upsert_updates_record_when_match_exists(client):
    client.list_records.return_value = [
        {"id": "rec456", "fields": {"Invoice Number": "INV-001"}}
    ]

    client.update_record.return_value = {
        "id": "rec456",
        "fields": {"Invoice Number": "INV-001-UPDATED"},
    }

    result = upsert_record_by_sqlite_id(
        client=client,
        table_name="Invoices",
        sqlite_id_field="SQLite Invoice ID",
        sqlite_id=10,
        fields={"Invoice Number": "INV-001-UPDATED"},
    )

    assert result["id"] == "rec456"

    client.update_record.assert_called_once_with(
        table_name="Invoices",
        record_id="rec456",
        fields={"Invoice Number": "INV-001-UPDATED"},
    )

    client.create_record.assert_not_called()


def test_upsert_rejects_multiple_matching_records(client):
    client.list_records.return_value = [
        {"id": "rec123", "fields": {}},
        {"id": "rec456", "fields": {}},
    ]

    with pytest.raises(AirtableDuplicateRecordError):
        upsert_record_by_sqlite_id(
            client=client,
            table_name="Invoices",
            sqlite_id_field="SQLite Invoice ID",
            sqlite_id=10,
            fields={"Invoice Number": "INV-001"},
        )

    client.create_record.assert_not_called()
    client.update_record.assert_not_called()


@pytest.mark.parametrize("invalid_id", [0, -1])
def test_upsert_rejects_invalid_sqlite_id(client, invalid_id):
    with pytest.raises(ValueError):
        upsert_record_by_sqlite_id(
            client=client,
            table_name="Invoices",
            sqlite_id_field="SQLite Invoice ID",
            sqlite_id=invalid_id,
            fields={"Invoice Number": "INV-001"},
        )

    client.list_records.assert_not_called()


def test_upsert_rejects_empty_table_name(client):
    with pytest.raises(ValueError):
        upsert_record_by_sqlite_id(
            client=client,
            table_name="",
            sqlite_id_field="SQLite Invoice ID",
            sqlite_id=10,
            fields={"Invoice Number": "INV-001"},
        )

    client.list_records.assert_not_called()


def test_upsert_rejects_empty_sqlite_id_field(client):
    with pytest.raises(ValueError):
        upsert_record_by_sqlite_id(
            client=client,
            table_name="Invoices",
            sqlite_id_field="",
            sqlite_id=10,
            fields={"Invoice Number": "INV-001"},
        )

    client.list_records.assert_not_called()