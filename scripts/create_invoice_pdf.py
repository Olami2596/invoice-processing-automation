
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


def create_invoice():
    output_path = Path("data/new_fictional_invoice.pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
        "<b>Apex Office Technologies</b><br/>"
        "15 Adeola Street<br/>"
        "Lagos, Nigeria",
        styles["Normal"],
    ))

    story.append(Spacer(1, 8 * mm))

    invoice_details = [
        ["Invoice Number:", "INV-2026-1102-001"],
        ["Invoice Date:", "November 2, 2026"],
        ["Due Date:", "November 16, 2026"],
        ["Customer:", "Greenfield Consulting Ltd."],
        ["Currency:", "NGN"],
    ]

    details_table = Table(
        invoice_details,
        colWidths=[45 * mm, 110 * mm],
    )

    details_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    story.append(details_table)
    story.append(Spacer(1, 10 * mm))

    line_items = [
        ["Description", "Quantity", "Unit Price (NGN)", "Amount (NGN)"],
        ["Business monitors", "3", "145000.00", "435000.00"],
        ["Ergonomic keyboards", "2", "42500.00", "85000.00"],
        ["Installation and support", "1", "75000.00", "75000.00"],
    ]

    items_table = Table(
        line_items,
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
        ["Subtotal:", "595000.00"],
        ["VAT (7.5%):", "44625.00"],
        ["Total:", "639625.00"],
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

    print(f"Invoice PDF created successfully: {output_path}")


if __name__ == "__main__":
    create_invoice()
