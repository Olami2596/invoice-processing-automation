from src.airtable_client import AirtableClient


def main():
    client = AirtableClient()

    records = client.list_records(
        table_name="Invoices",
        page_size=1,
    )

    print("Airtable connection successful.")
    print(f"Records retrieved: {len(records)}")


if __name__ == "__main__":
    main()