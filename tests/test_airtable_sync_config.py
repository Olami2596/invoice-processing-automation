
import pytest

from src import airtable_sync


def test_get_airtable_table_config_reads_environment_variables(
    monkeypatch,
):
    monkeypatch.setattr(airtable_sync, "load_dotenv", lambda: None)

    monkeypatch.setenv("AIRTABLE_INVOICES_TABLE", "Test Invoices")
    monkeypatch.setenv("AIRTABLE_DRAFTS_TABLE", "Test Drafts")

    config = airtable_sync.get_airtable_table_config()

    assert config == {
        "invoices": "Test Invoices",
        "drafts": "Test Drafts",
    }


def test_get_airtable_table_config_rejects_missing_configuration(
    monkeypatch,
):
    monkeypatch.setattr(airtable_sync, "load_dotenv", lambda: None)

    monkeypatch.delenv("AIRTABLE_INVOICES_TABLE", raising=False)
    monkeypatch.delenv("AIRTABLE_DRAFTS_TABLE", raising=False)

    with pytest.raises(
        airtable_sync.AirtableSyncConfigurationError
    ):
        airtable_sync.get_airtable_table_config()


def test_get_airtable_table_config_rejects_blank_table_names(
    monkeypatch,
):
    monkeypatch.setattr(airtable_sync, "load_dotenv", lambda: None)

    monkeypatch.setenv("AIRTABLE_INVOICES_TABLE", "   ")
    monkeypatch.setenv("AIRTABLE_DRAFTS_TABLE", "Test Drafts")

    with pytest.raises(
        airtable_sync.AirtableSyncConfigurationError
    ):
        airtable_sync.get_airtable_table_config()


def test_invoice_sync_uses_configured_table_name(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        airtable_sync,
        "get_airtable_table_config",
        lambda: {
            "invoices": "Custom Invoices",
            "drafts": "Custom Drafts",
        },
    )

    monkeypatch.setattr(
        airtable_sync,
        "invoice_to_airtable_fields",
        lambda **kwargs: {"Invoice Number": "TEST-001"},
    )

    def fake_upsert(**kwargs):
        captured.update(kwargs)
        return {"id": "rec123"}

    monkeypatch.setattr(
        airtable_sync,
        "upsert_record_by_sqlite_id",
        fake_upsert,
    )

    result = airtable_sync.sync_invoice_to_airtable(
        client=object(),
        invoice=object(),
        source_file="test.pdf",
        sqlite_invoice_id=1,
    )

    assert result == {"id": "rec123"}
    assert captured["table_name"] == "Custom Invoices"
    assert captured["sqlite_id_field"] == "SQLite Invoice ID"


def test_draft_sync_uses_configured_table_name(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        airtable_sync,
        "get_airtable_table_config",
        lambda: {
            "invoices": "Custom Invoices",
            "drafts": "Custom Drafts",
        },
    )

    monkeypatch.setattr(
        airtable_sync,
        "quickbooks_draft_to_airtable_fields",
        lambda **kwargs: {"Bill Number": "TEST-002"},
    )

    def fake_upsert(**kwargs):
        captured.update(kwargs)
        return {"id": "rec456"}

    monkeypatch.setattr(
        airtable_sync,
        "upsert_record_by_sqlite_id",
        fake_upsert,
    )

    result = airtable_sync.sync_quickbooks_draft_to_airtable(
        client=object(),
        draft=object(),
        sqlite_draft_id=2,
    )

    assert result == {"id": "rec456"}
    assert captured["table_name"] == "Custom Drafts"
    assert captured["sqlite_id_field"] == "SQLite Draft ID"
