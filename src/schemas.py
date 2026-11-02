from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Literal

class InvoiceLineItem(BaseModel):
    description: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    amount: Decimal = Field(ge=0)

class Invoice(BaseModel):
    vendor_name: str = Field(min_length=1)
    customer_name: str = Field(min_length=1)
    invoice_number: str = Field(min_length=1)
    invoice_date: date
    due_date: date | None = None
    currency: str = Field(min_length=1)
    line_items: list[InvoiceLineItem] = Field(min_length=1)
    subtotal: Decimal = Field(ge=0)
    tax_amount: Decimal | None = Field(default=None, ge=0)
    total_amount: Decimal = Field(ge=0)

class InvoiceProcessingResult(BaseModel):
    success: bool
    invoice: Invoice
    errors: list[str] = Field(default_factory=list)
    source_file: str = Field(min_length=1)


class QuickBooksBillLineItem(BaseModel):
    """Represents an individual line item in a QuickBooks bill draft."""

    description: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    amount: Decimal = Field(ge=0)


class QuickBooksBillDraft(BaseModel):
    """Represents a simplified QuickBooks-style bill draft."""

    vendor_name: str = Field(min_length=1)
    bill_number: str = Field(min_length=1)
    bill_date: date
    due_date: date | None = None
    currency: str = Field(min_length=1)

    line_items: list[QuickBooksBillLineItem] = Field(min_length=1)

    subtotal: Decimal = Field(ge=0)
    tax_amount: Decimal | None = Field(default=None, ge=0)
    total_amount: Decimal = Field(ge=0)

    status: Literal["draft"] = "draft"
