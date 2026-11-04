
import random
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


VENDORS = [
    ("Apex Office Technologies", "15 Adeola Street, Lagos"),
    ("NovaTech Solutions", "22 Marina Road, Lagos"),
    ("Brightline Systems", "8 Allen Avenue, Ikeja"),
    ("Vertex Business Supplies", "14 Broad Street, Lagos"),
    ("CloudBridge Technologies", "31 Admiralty Way, Lekki"),
]

CUSTOMERS = [
    "Greenfield Consulting Ltd.",
    "BluePeak Enterprises",
    "Meridian Business Group",
    "Oakwood Technologies Ltd.",
    "Silverline Creative Agency",
]

PRODUCTS = [
    ("Business laptops", Decimal("285000.00")),
    ("Computer monitors", Decimal("145000.00")),
    ("Wireless keyboards", Decimal("42500.00")),
    ("Network routers", Decimal("85000.00")),
    ("External hard drives", Decimal("65000.00")),
    ("Installation and support", Decimal("75000.00")),
    ("Cloud backup configuration", Decimal("60000.00")),
    ("Office printers", Decimal("195000.00")),
]


def generate_invoice_number():
    """Generate a unique invoice number."""

    today = date.today().strftime("%Y%m%d")
    unique_suffix = uuid.uuid4().hex[:8].upper()

    return f"INV-{today}-{unique_suffix}"


def generate_line_items():
    """Generate random invoice line items with valid calculations."""

    selected_products = random.sample(
        PRODUCTS,
        k=random.randint(2, 4),
    )

    line_items = []

    for description, unit_price in selected_products:
        quantity = random.randint(1, 5)
        amount = unit_price * quantity

        line_items.append({
            "description": description,
            "quantity": quantity,
            "unit_price": unit_price,
            "amount": amount,
        })

    return line_items


def create_invoice_pdf(invoice_data, output_path):
    """Generate a PDF invoice from structured invoice data."""

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontSize=24,
        alignment=TA_RIGHT,
    )

    story = []

    story.append(Paragraph("INVOICE", title_style))
    story.append(Spacer(1, 10 * mm))

    story.append(Paragraph(
        f"<b>{invoice_data['vendor_name']}</b><br/>"
        f"{invoice_data['vendor_address']}",
        styles["Normal"],
    ))

    story.append(Spacer(1, 8 * mm))

    details = [
        ["Invoice Number:", invoice_data["invoice_number"]],
        ["Invoice Date:", invoice_data["invoice_date"].isoformat()],
        ["Due Date:", invoice_data["due_date"].isoformat()],
        ["Customer:", invoice_data["customer_name"]],
        ["Currency:", "NGN"],
    ]

    details_table = Table(
        details,
        colWidths=[45 * mm, 110 * mm],
    )

    details_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    story.append(details_table)
    story.append(Spacer(1, 10 * mm))

    table_data = [[
        "Description",
        "Quantity",
        "Unit Price (NGN)",
        "Amount (NGN)",
    ]]

    for item in invoice_data["line_items"]:
        table_data.append([
            item["description"],
            str(item["quantity"]),
            f"{item['unit_price']:,.2f}",
            f"{item['amount']:,.2f}",
        ])

    items_table = Table(
        table_data,
        colWidths=[65 * mm, 25 * mm, 40 * mm, 40 * mm],
    )

    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243B53")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
    ]))

    story.append(items_table)
    story.append(Spacer(1, 10 * mm))

    totals = [
        ["Subtotal:", f"{invoice_data['subtotal']:,.2f}"],
        ["VAT (7.5%):", f"{invoice_data['tax_amount']:,.2f}"],
        ["Total:", f"{invoice_data['total_amount']:,.2f}"],
    ]

    totals_table = Table(
        totals,
        colWidths=[120 * mm, 50 * mm],
    )

    totals_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
    ]))

    story.append(totals_table)
    story.append(Spacer(1, 15 * mm))

    story.append(Paragraph(
        "Thank you for your business.",
        styles["Normal"],
    ))

    document.build(story)


def generate_test_invoice(output_directory="data"):
    """
    Generate a new fictional invoice and return its PDF path.
    """

    invoice_number = generate_invoice_number()

    vendor_name, vendor_address = random.choice(VENDORS)
    customer_name = random.choice(CUSTOMERS)

    invoice_date = date.today()
    due_date = invoice_date + timedelta(days=14)

    line_items = generate_line_items()

    subtotal = sum(
        (item["amount"] for item in line_items),
        Decimal("0.00"),
    )

    tax_amount = (subtotal * Decimal("0.075")).quantize(
        Decimal("0.01")
    )

    total_amount = subtotal + tax_amount

    invoice_data = {
        "invoice_number": invoice_number,
        "vendor_name": vendor_name,
        "vendor_address": vendor_address,
        "customer_name": customer_name,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "line_items": line_items,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
    }

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    output_path = output_directory / f"{invoice_number}.pdf"

    create_invoice_pdf(invoice_data, output_path)

    print("=" * 55)
    print("NEW TEST INVOICE GENERATED")
    print("=" * 55)
    print(f"Invoice number: {invoice_number}")
    print(f"Vendor: {vendor_name}")
    print(f"Customer: {customer_name}")
    print(f"Subtotal: NGN {subtotal:,.2f}")
    print(f"VAT: NGN {tax_amount:,.2f}")
    print(f"Total: NGN {total_amount:,.2f}")
    print(f"PDF location: {output_path}")
    print("=" * 55)

    return output_path


if __name__ == "__main__":
    generate_test_invoice()
