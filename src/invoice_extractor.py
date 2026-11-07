
"""Extract structured invoice data using a local AI model."""

import json
import re
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.schemas import Invoice


def generate_with_ollama(prompt):
    request_data = {
        "model": "qwen2.5:1.5b",
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    encoded_data = json.dumps(request_data).encode("utf-8")

    request = Request(
        url="http://localhost:11434/api/generate",
        data=encoded_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=360) as response:
        response_bytes = response.read()
        response_text = response_bytes.decode("utf-8")
        response_data = json.loads(response_text)

    return response_data["response"]


def normalise_monetary_value(value):
    """
    Convert correctly comma-formatted monetary strings into Decimal.

    Examples:
        "65,000.00" -> Decimal("65000.00")
        "145,000"   -> Decimal("145000")
        "65000.00"  -> Decimal("65000.00")

    Invalid or unexpected strings are left unchanged so that
    Pydantic can reject them during validation.
    """

    if not isinstance(value, str):
        return value

    value = value.strip()

    # Accept ordinary decimal numbers and correctly grouped
    # thousands separators.
    monetary_pattern = (
        r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    )

    if re.fullmatch(monetary_pattern, value):
        return Decimal(value.replace(",", ""))

    return value


def normalise_invoice_amounts(invoice_data):
    """
    Normalise monetary fields in the invoice extraction response.

    This includes invoice line items, subtotal, tax and total.
    The original dictionary is updated and returned.
    """

    monetary_fields = (
        "unit_price",
        "amount",
        "subtotal",
        "tax_amount",
        "total_amount",
    )

    for line_item in invoice_data.get("line_items", []):
        if isinstance(line_item, dict):
            for field in ("unit_price", "amount"):
                if field in line_item:
                    line_item[field] = normalise_monetary_value(
                        line_item[field]
                    )

    for field in ("subtotal", "tax_amount", "total_amount"):
        if field in invoice_data:
            invoice_data[field] = normalise_monetary_value(
                invoice_data[field]
            )

    return invoice_data


def extract_invoice_data(invoice_text):
    """Extract structured invoice data from plain invoice text."""

    prompt = f"""
You are an invoice data extraction assistant.

Extract structured data from the invoice text provided below.

RULES:
1. Extract only information explicitly supported by the invoice text.
2. Never invent, assume, or fabricate missing values.
3. Return a single valid JSON object using exactly these field names:
   vendor_name, customer_name, invoice_number, invoice_date,
   due_date, currency, line_items, subtotal, tax_amount, total_amount.
4. Represent missing optional values as null.
5. Represent line_items as a JSON list of objects. Each object must
   contain description, quantity, unit_price, and amount.
6. Preserve invoice numbers and other identifiers exactly as written.
7. Preserve monetary values accurately. Do not change their values
   or perform calculations to fill in missing amounts.
8. Use ISO date format YYYY-MM-DD for dates when the source provides
   enough information to determine the date unambiguously.
9. Use JSON numbers or decimal strings for numeric values, not
   formatted currency strings. Do not include currency symbols in
   numeric values. Do not use commas as thousands separators.
10. If a required field is missing, use null rather than inventing
    a value. The application will validate required fields later.
11. Return JSON only. Do not include Markdown fences or explanations.

INVOICE TEXT:
{invoice_text}
"""

    raw_response = generate_with_ollama(prompt)

    invoice_data = json.loads(
        raw_response,
        parse_float=Decimal,
        parse_int=Decimal,
    )

    invoice_data = normalise_invoice_amounts(invoice_data)

    return Invoice.model_validate(invoice_data)
