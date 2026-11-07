
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

from src.invoice_generator import generate_test_invoice


def send_test_invoice_email():
    """Generate a fictional invoice and send it to Mailpit."""

    load_dotenv()

    smtp_host = os.getenv("SMTP_HOST", "localhost")
    smtp_port = int(os.getenv("SMTP_PORT", "1025"))

    sender = os.getenv(
        "EMAIL_SENDER",
        "automation@invoiceprocessor.local",
    )

    recipient = os.getenv(
        "EMAIL_RECIPIENT",
        "invoices@invoiceprocessor.local",
    )

    # Generate a brand-new invoice PDF.
    pdf_path = Path(generate_test_invoice())

    message = EmailMessage()
    message["Subject"] = f"Invoice Submission - {pdf_path.stem}"
    message["From"] = sender
    message["To"] = recipient

    message.set_content(
        "Hello,\n\n"
        "Please find the attached invoice for processing.\n\n"
        "This is a fictional invoice generated for testing "
        "the invoice processing automation system.\n\n"
        "Regards,\n"
        "Invoice Automation System"
    )

    # Attach the generated invoice PDF.
    with open(pdf_path, "rb") as invoice_file:
        message.add_attachment(
            invoice_file.read(),
            maintype="application",
            subtype="pdf",
            filename=pdf_path.name,
        )

    # Send the email through Mailpit.
    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.send_message(message)

    print("Test email sent successfully!")
    print(f"Recipient: {recipient}")
    print(f"Invoice PDF: {pdf_path}")
    print(f"Invoice number: {pdf_path.stem}")


if __name__ == "__main__":
    send_test_invoice_email()
