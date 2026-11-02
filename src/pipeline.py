"""
Invoice processing pipeline.

Orchestrates the extraction of text from invoice PDFs,
the extraction of structured invoice data using AI,
and the validation of extracted invoices against
defined business rules.
"""
from src.pdf_extractor import extract_text_from_pdf
from src.invoice_extractor import extract_invoice_data
from src.validation import validate_invoice
from src.schemas import InvoiceProcessingResult


def process_invoice(pdf_path, existing_invoices=None):
    """
    Process an invoice PDF from text extraction through
    AI extraction and business validation.

    Args:
        pdf_path: Path to the invoice PDF.
        existing_invoices: Previously processed invoices.

    Returns:
        An InvoiceProcessingResult containing the extracted
        invoice, validation status, errors, and source file.
    """

    # 1. Use an empty list if no existing invoices are provided.
    if existing_invoices is None:
        existing_invoices = []

    # 2. Extract text from the PDF.
    invoice_text = extract_text_from_pdf(pdf_path)

    # 3. Extract structured invoice data using AI.
    invoice = extract_invoice_data(invoice_text)

    # 4. Validate the extracted invoice.
    errors = validate_invoice(invoice, existing_invoices)

    # 5. Create and return the processing result.
    return InvoiceProcessingResult(
        success=len(errors) == 0,
        invoice=invoice,
        errors=errors,
        source_file=str(pdf_path),
    )
