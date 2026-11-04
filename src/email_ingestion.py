
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


def get_mailpit_api_url():
    """Return the configured Mailpit API URL."""

    load_dotenv()

    return os.getenv(
        "MAILPIT_API_URL",
        "http://localhost:8025/api/v1",
    ).rstrip("/")


def api_get(url):
    """Send a GET request to the Mailpit API."""

    request = Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )

    with urlopen(request, timeout=30) as response:
        return response.read()


def get_field(data, field_name):
    """Retrieve a dictionary field without depending on its casing."""

    if not isinstance(data, dict):
        return None

    for key, value in data.items():
        if key.lower() == field_name.lower():
            return value

    return None


def search_emails(query, start=0, limit=50):
    """
    Search Mailpit emails using its search API.

    Returns a list of matching message summaries.
    """

    api_url = get_mailpit_api_url()

    parameters = urlencode({
        "query": query,
        "start": start,
        "limit": limit,
    })

    url = f"{api_url}/search?{parameters}"

    response_bytes = api_get(url)
    response_data = json.loads(response_bytes.decode("utf-8"))

    messages = get_field(response_data, "messages")

    if not isinstance(messages, list):
        raise ValueError(
            "Unexpected Mailpit search response: "
            "messages list was not found."
        )

    return messages


def get_email_details(message_id):
    """Retrieve the full details of an email."""

    api_url = get_mailpit_api_url()
    url = f"{api_url}/message/{message_id}"

    response_bytes = api_get(url)

    return json.loads(response_bytes.decode("utf-8"))


def download_pdf_attachments(
    message_id,
    output_directory="data/email_attachments",
):
    """
    Download all PDF attachments from a Mailpit email.

    Returns a list of downloaded file paths.
    """

    api_url = get_mailpit_api_url()

    message_data = get_email_details(message_id)

    attachments = get_field(message_data, "Attachments") or []

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    downloaded_files = []

    for attachment in attachments:
        filename = get_field(attachment, "FileName") or ""
        content_type = get_field(attachment, "ContentType") or ""

        is_pdf = (
            filename.lower().endswith(".pdf")
            or content_type.lower() == "application/pdf"
        )

        if not is_pdf:
            continue

        part_id = get_field(attachment, "PartID")

        if not filename or not part_id:
            raise ValueError(
                "PDF attachment is missing its filename or PartID."
            )

        # Prevent attachment filenames from writing outside
        # the intended output directory.
        safe_filename = Path(filename).name

        if safe_filename != filename or safe_filename in ("", ".", ".."):
            raise ValueError("Unsafe attachment filename received.")

        if not safe_filename.lower().endswith(".pdf"):
            raise ValueError("Attachment filename must end in .pdf.")

        output_path = output_directory / safe_filename

        if output_path.exists():
            raise FileExistsError(
                f"Attachment already exists: {output_path}"
            )

        attachment_url = (
            f"{api_url}/message/{message_id}/part/{part_id}"
        )

        pdf_bytes = api_get(attachment_url)

        if not pdf_bytes.startswith(b"%PDF-"):
            raise ValueError(
                f"Downloaded attachment is not a valid PDF: "
                f"{safe_filename}"
            )

        output_path.write_bytes(pdf_bytes)
        downloaded_files.append(output_path)

    return downloaded_files


def ingest_invoice_email(
    invoice_number,
    output_directory="data/email_attachments",
):
    """
    Find an invoice email and download its PDF attachments.

    Returns the downloaded PDF paths.
    """

    query = f'subject:"{invoice_number}"'

    messages = search_emails(query)

    matching_message = None

    for message in messages:
        subject = get_field(message, "Subject") or ""

        if invoice_number in subject:
            matching_message = message
            break

    if matching_message is None:
        raise LookupError(
            f"No email found for invoice {invoice_number}."
        )

    message_id = get_field(matching_message, "ID")

    if not message_id:
        raise ValueError(
            "Mailpit search result did not contain a message ID."
        )

    downloaded_files = download_pdf_attachments(
        message_id=message_id,
        output_directory=output_directory,
    )

    if not downloaded_files:
        raise FileNotFoundError(
            f"No PDF attachments found for invoice {invoice_number}."
        )

    return downloaded_files
