from src.pipeline import process_recent_invoice_emails
from src.storage import initialise_database


def main():
    # Ensure all database tables exist before processing emails.
    initialise_database()

    results = process_recent_invoice_emails()

    if not results:
        print("No new invoice emails were available for processing.")
        return

    for result in results:
        print("\nEmail processing result")
        print("-----------------------")
        print(f"Message ID: {result['message_id']}")
        print(f"Subject: {result['subject']}")
        print(f"Status: {result['status']}")
        print(f"Processed files: {result['processed_files']}")
        print(f"Errors: {result['errors']}")


if __name__ == "__main__":
    main()