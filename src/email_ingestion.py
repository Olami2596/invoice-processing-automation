
import json
import os
import logging
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from src import storage

from src.logging_config import LOGGER_NAME
from dotenv import load_dotenv

logger = logging.getLogger(LOGGER_NAME)

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


def get_recent_emails(start=0, limit=50):
    """
    Retrieve recent emails from Mailpit.

    Messages are returned from newest to oldest.

    Args:
        start: Pagination offset.
        limit: Maximum number of messages to retrieve.

    Returns:
        A list of message summaries.
    """

    if start < 0:
        raise ValueError("start cannot be negative.")

    if limit < 1:
        raise ValueError("limit must be at least 1.")

    api_url = get_mailpit_api_url()

    parameters = urlencode({
        "start": start,
        "limit": limit,
    })

    url = f"{api_url}/messages?{parameters}"

    response_bytes = api_get(url)
    response_data = json.loads(response_bytes.decode("utf-8"))

    messages = get_field(response_data, "messages")

    if not isinstance(messages, list):
        raise ValueError(
            "Unexpected Mailpit response: "
            "messages list was not found."
        )

    return messages

def get_email_details(message_id):
    """Retrieve the full details of an email."""

    api_url = get_mailpit_api_url()
    url = f"{api_url}/message/{message_id}"

    response_bytes = api_get(url)

    return json.loads(response_bytes.decode("utf-8"))


def get_pdf_attachments(message_id):
    """
    Retrieve PDF attachment metadata for a specific email.

    Returns a list of PDF attachment metadata dictionaries.
    """

    message_data = get_email_details(message_id)

    attachments = get_field(message_data, "Attachments") or []

    pdf_attachments = []

    for attachment in attachments:
        filename = get_field(attachment, "FileName") or ""
        content_type = get_field(attachment, "ContentType") or ""

        is_pdf = (
            filename.lower().endswith(".pdf")
            or content_type.lower() == "application/pdf"
        )

        if is_pdf:
            pdf_attachments.append(attachment)

    return pdf_attachments



def download_pdf_attachments(
    message_id,
    output_directory="data/email_attachments",
    use_tracking=False,
):
    """
    Download PDF attachments from a Mailpit email.

    When use_tracking=True, previously downloaded attachments
    are reused instead of creating duplicate files.

    Returns a list of downloaded or reused PDF paths.
    """

    api_url = get_mailpit_api_url()
    pdf_attachments = get_pdf_attachments(message_id)

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    downloaded_files = []

    for attachment in pdf_attachments:
        filename = get_field(attachment, "FileName") or ""
        part_id = get_field(attachment, "PartID")

        if not filename or not part_id:
            raise ValueError(
                "PDF attachment is missing its filename or PartID."
            )

        # Prevent directory traversal.
        safe_filename = Path(filename).name

        if safe_filename != filename or safe_filename in ("", ".", ".."):
            raise ValueError("Unsafe attachment filename received.")

        if not safe_filename.lower().endswith(".pdf"):
            raise ValueError("Attachment filename must end in .pdf.")

        record = None

        if use_tracking:
            record = storage.get_email_attachment_record(
                message_id,
                part_id,
            )

            if record is None:
                storage.register_email_attachment(
                    message_id,
                    part_id,
                    safe_filename,
                )

                record = storage.get_email_attachment_record(
                    message_id,
                    part_id,
                )

        # Reuse an existing valid attachment file.
        if record and record["file_path"]:
            existing_path = Path(record["file_path"])

            if existing_path.is_file():
                existing_bytes = existing_path.read_bytes()

                if existing_bytes.startswith(b"%PDF-"):
                    downloaded_files.append(existing_path)
                    continue

        # Reuse the recorded path if the file needs to be downloaded again.
        if record and record["file_path"]:
            output_path = Path(record["file_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)

        else:
            # Preserve the original filename where possible.
            output_path = output_directory / safe_filename

            # Avoid overwriting unrelated files.
            counter = 1

            while output_path.exists():
                output_path = (
                    output_directory
                    / f"{Path(safe_filename).stem}_{counter}.pdf"
                )
                counter += 1

        attachment_url = (
            f"{api_url}/message/{message_id}/part/{part_id}"
        )

        try:
            pdf_bytes = api_get(attachment_url)

            if not pdf_bytes.startswith(b"%PDF-"):
                raise ValueError(
                    f"Downloaded attachment is not a valid PDF: "
                    f"{safe_filename}"
                )

            output_path.write_bytes(pdf_bytes)

            if use_tracking:
                storage.mark_attachment_downloaded(
                    message_id,
                    part_id,
                    str(output_path),
                )

            downloaded_files.append(output_path)

        except Exception as error:
            if use_tracking:
                storage.mark_attachment_failed(
                    message_id,
                    part_id,
                    str(error),
                )

            raise

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



def ingest_recent_invoice_emails(
    start: int = 0,
    limit: int = 10,
    output_directory: str | Path = "data/incoming",
) -> list[dict]:
    """
    Retrieve recent emails and download their PDF attachments.

    A failure affecting one email should not prevent the remaining
    emails from being processed.

    Sensitive email details and raw exception messages are not written
    to application logs.
    """

    try:
        messages = get_recent_emails(start=start, limit=limit)

    except Exception as error:
        logger.error(
            "Recent email retrieval failed (%s).",
            type(error).__name__,
        )
        raise

    logger.info(
        "Retrieved %s recent email(s).",
        len(messages),
    )

    results = []

    for message in messages:
        message_id = get_field(message, "ID")
        subject = get_field(message, "Subject") or ""

        if not message_id:
            logger.warning("Skipping email without a message ID.")
            continue

        # Register the email and check whether it is eligible for processing.
        try:
            storage.register_email(message_id, subject)

        except Exception as error:
            logger.error(
                "Email registration failed (%s).",
                type(error).__name__,
            )
            continue

        try:
            should_process = storage.should_process_email(message_id)

        except Exception as error:
            logger.error(
                "Email retry eligibility check failed (%s).",
                type(error).__name__,
            )

            try:
                storage.mark_email_failed(
                    message_id,
                    "Email retry eligibility check failed.",
                    failure_type="transient",
                )
            except Exception as recording_error:
                logger.error(
                    "Could not record email failure (%s).",
                    type(recording_error).__name__,
                )

            continue

        if not should_process:
            logger.info("Email skipped because it is not eligible for processing.")
            continue

        logger.info("Processing an eligible email.")

        try:
            attachments = get_pdf_attachments(message_id)

            if not attachments:
                storage.mark_email_failed(
                    message_id,
                    "No PDF attachments found.",
                )

                logger.warning("Email contains no PDF attachments.")
                continue

            # Register attachment records before downloading.
            for attachment in attachments:
                filename = get_field(attachment, "FileName")
                part_id = get_field(attachment, "PartID")

                if not filename or not part_id:
                    raise ValueError(
                        "Attachment is missing required metadata."
                    )

                storage.register_email_attachment(
                    message_id,
                    part_id,
                    filename,
                )

            downloaded_files = download_pdf_attachments(
                message_id,
                output_directory,
                use_tracking=True,
            )

            if not downloaded_files:
                storage.mark_email_failed(
                    message_id,
                    "No PDF attachments were downloaded.",
                )

                logger.warning("No PDF attachments were downloaded.")
                continue

            results.append(
                {
                    "message_id": message_id,
                    "subject": subject,
                    "downloaded_files": downloaded_files,
                }
            )

            logger.info(
                "Email attachment ingestion completed successfully."
            )

        except Exception as error:
            logger.error(
                "Email attachment ingestion failed (%s).",
                type(error).__name__,
            )

            try:
                storage.mark_email_failed(
                    message_id,
                    str(error),
                )
            except Exception as recording_error:
                logger.error(
                    "Could not record email failure (%s).",
                    type(recording_error).__name__,
                )

            continue

    return results