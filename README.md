# Invoice Processing Automation

An AI-powered invoice processing pipeline built with Python. The application retrieves invoice emails, extracts invoice data from PDF attachments, uses a local language model to structure the information, validates the results, and stores invoices and accounting drafts in SQLite.

It also supports Airtable synchronization and Slack notifications.

## Features

- **Email ingestion:** Retrieve recent invoice emails from the configured local email environment.
- **PDF extraction:** Extract text from invoice PDF attachments using `pdfplumber`.
- **AI-powered extraction:** Use Ollama and a local language model to extract structured invoice information.
- **Data validation:** Validate extracted invoice data using Pydantic schemas and business rules.
- **Duplicate detection:** Identify duplicate invoices and prevent unintended duplicate processing.
- **SQLite persistence:** Store invoices, QuickBooks-style drafts, email processing records, and attachment processing records.
- **Airtable synchronization:** Queue and synchronize invoice and draft records with Airtable, including retries and failure handling.
- **Slack notifications:** Send notifications about invoice processing and Airtable synchronization events.
- **Reliability:** Support retry handling, idempotent processing, structured logging, and recovery from partial failures.
- **Automated tests:** Test core functionality, integrations, validation, and failure scenarios.

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.14 |
| Package management | uv |
| PDF extraction | pdfplumber |
| AI model runtime | Ollama |
| Local AI model | Qwen 2.5 1.5B |
| Data validation | Pydantic |
| Database | SQLite |
| Email testing | Mailpit |
| External record synchronization | Airtable API |
| Notifications | Slack Incoming Webhooks |
| Testing | pytest |

## Project Structure

```text
invoice-processing-automation/
│
├── data/
│   └── fictional_invoice.pdf
│
├── logs/
│
├── scripts/
│   ├── create_invoice_pdf.py
│   ├── test_airtable_connection.py
│   ├── test_process_recent_emails.py
│   └── test_slack_connection.py
│
├── src/
│   ├── airtable_client.py
│   ├── airtable_sync.py
│   ├── airtable_worker.py
│   ├── email_ingestion.py
│   ├── invoice_extractor.py
│   ├── invoice_generator.py
│   ├── logging_config.py
│   ├── notifications.py
│   ├── pdf_extractor.py
│   ├── pipeline.py
│   ├── quickbooks.py
│   ├── schemas.py
│   ├── storage.py
│   └── validation.py
│
├── tests/
│
├── .env.example
├── .gitignore
├── main.py
├── sync_airtable.py
├── pyproject.toml
├── uv.lock
└── README.md
```

Runtime databases, generated invoices, downloaded email attachments, logs, and environment secrets are kept out of version control.

## Prerequisites

Install the following before running the application:

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/)
- [Mailpit](https://mailpit.axllent.org/) for local email testing

Airtable and Slack credentials are required only when using their respective integrations.

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd invoice-processing-automation
```

Install project dependencies:

```bash
uv sync --dev
```

Activate the virtual environment in PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

## Configuration

Create your local environment file:

```powershell
Copy-Item .env.example .env
```

Configure the variables in `.env`:

```dotenv
SMTP_HOST=localhost
SMTP_PORT=1025
EMAIL_SENDER=
EMAIL_RECIPIENT=

MAILPIT_API_URL=http://localhost:8025/api/v1

AIRTABLE_PAT=
AIRTABLE_BASE_ID=
AIRTABLE_INVOICES_TABLE=Invoices
AIRTABLE_DRAFTS_TABLE=QuickBooks Drafts

SLACK_WEBHOOK_URL=
```

### Configuration details

| Variable | Purpose |
|---|---|
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_PORT` | SMTP server port |
| `EMAIL_SENDER` | Sender address for test emails |
| `EMAIL_RECIPIENT` | Recipient address for test emails |
| `MAILPIT_API_URL` | Mailpit REST API endpoint |
| `AIRTABLE_PAT` | Airtable Personal Access Token |
| `AIRTABLE_BASE_ID` | Airtable base identifier |
| `AIRTABLE_INVOICES_TABLE` | Airtable invoice table |
| `AIRTABLE_DRAFTS_TABLE` | Airtable draft table |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |

Do not commit `.env` or expose API tokens and webhook URLs. Use `.env.example` as the safe configuration template.

## Local AI Setup

Install Ollama and pull the model:

```bash
ollama pull qwen2.5:1.5b
```

Ensure Ollama is running locally and the model is available:

```bash
ollama list
```

The application uses the local Ollama API at:

```text
http://localhost:11434/api/generate
```

No external hosted LLM API key is required for the configured local model.

## Email Testing with Mailpit

Start Mailpit and confirm its services are available:

- SMTP: `localhost:1025`
- Web interface: `http://localhost:8025`
- REST API: `http://localhost:8025/api/v1`

To generate and send a fresh fictional invoice email:

```bash
python test_send_email.py
```

The script generates a fictional invoice with a unique invoice number and sends it through the configured local SMTP server.

You can inspect received messages and attachments through the Mailpit web interface.

## Running the Application

### Process recent invoice emails

Run the default application command:

```bash
python main.py
```

Limit the number of emails processed:

```bash
python main.py --limit 10
```

Use pagination to start from a particular email offset:

```bash
python main.py --start 10 --limit 20
```

### Process a single PDF

```bash
python main.py --pdf data/fictional_invoice.pdf
```

The application initializes the SQLite database and runs the required database migrations automatically at startup.

## Airtable Synchronization

Invoice and accounting draft records are placed in a local synchronization queue.

Run the standalone worker:

```bash
python sync_airtable.py
```

Limit the number of queued jobs processed:

```bash
python sync_airtable.py --limit 10
```

The worker supports retry scheduling, failure classification, lease-based job claiming, and manual retry recovery.

**Note:** Running the worker can make real Airtable API requests and update your Airtable base. Configure the Airtable credentials and tables before running it.

## Slack Notifications

Configure `SLACK_WEBHOOK_URL` in `.env` to enable Slack notifications.

The application can send notifications for invoice processing and Airtable synchronization events.

A valid Slack Incoming Webhook is required for live notifications. Automated tests use mocked notification functions to avoid sending real Slack messages.

## Manual Integration Scripts

The `scripts/` directory contains utilities for manually testing or demonstrating individual components.

| Script | Purpose |
|---|---|
| `scripts/create_invoice_pdf.py` | Generate a sample invoice PDF |
| `scripts/test_airtable_connection.py` | Test Airtable API connectivity |
| `scripts/test_process_recent_emails.py` | Manually process recent invoice emails |
| `scripts/test_slack_connection.py` | Test Slack notification delivery |

These scripts are intended for explicit manual execution, not application startup or automated test execution.

Some scripts interact with live services or process existing emails. Review their effects before running them.

## Running Tests

Run the complete test suite:

```bash
python -m pytest -v
```

Run a specific test module:

```bash
python -m pytest tests/test_pipeline.py -v
```

Run tests with a summary:

```bash
python -m pytest
```

The test suite covers PDF extraction, AI extraction, validation, database persistence, email processing, Airtable synchronization, retry handling, Slack notifications, and failure recovery.

External notification and integration side effects are isolated where appropriate through mocks and test fixtures.

## Database and Logging

The application uses SQLite for persistent local storage.

The primary database is:

```text
data/invoices.db
```

The database stores invoice records, QuickBooks-style draft records, email processing information, attachment tracking, and Airtable synchronization jobs.

Application logs are written to:

```text
logs/processing.log
```

Generated files, databases, downloaded attachments, logs, and secrets are excluded from Git through `.gitignore`.

## QuickBooks Drafts

The application transforms validated invoice information into QuickBooks-style accounting draft records and stores them locally.

This is a mock/local draft workflow. A live QuickBooks API integration is not currently implemented.

## Security Considerations

- Store credentials and webhook URLs in `.env`.
- Never commit `.env` or real credentials.
- Use `.env.example` to document required configuration.
- Keep runtime databases and generated invoice documents out of version control.
- Use fictional invoices and local Mailpit infrastructure when testing email workflows.
- Avoid running integration scripts against production services unless intended.

## Project Status

The core invoice processing pipeline is implemented, with automated tests and local end-to-end workflow verification.

The project includes email ingestion, PDF extraction, AI-based invoice extraction, validation, SQLite persistence, QuickBooks-style draft generation, Airtable synchronization, and Slack notifications.

Further development may include additional accounting integrations, deployment improvements, and expanded monitoring.