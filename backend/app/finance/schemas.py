import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.enums import FinanceEntryKind
from app.common.validation import check_date, clean_text

MAX_AMOUNT = Decimal("999999999999.99")
_CURRENCY = re.compile(r"^[A-Z]{3}$")

Money = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]


class BudgetSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0, description="`version` from GET /finance; 0 for the first budget.")
    amount: Money = Field(ge=0, le=MAX_AMOUNT)
    currency: str = Field(default="EUR", description="Three capital letters, for example EUR.")

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        value = value.strip().upper()
        if not _CURRENCY.fullmatch(value):
            raise ValueError("Use a three-letter currency code, for example EUR.")
        return value


class FinanceEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: FinanceEntryKind
    amount: Money = Field(gt=0, le=MAX_AMOUNT)
    entry_date: date
    description: str = Field(max_length=500)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return clean_text(value, label="Description")

    @field_validator("entry_date")
    @classmethod
    def _date(cls, value: date) -> date:
        checked = check_date(value, "entry_date")
        assert checked is not None
        return checked


class FinanceOut(BaseModel):
    """Planned against spent, as in OpenProject's budgets, plus what the client has paid."""

    budget: Decimal | None = Field(description="Empty until a budget is set.")
    currency: str | None
    version: int = Field(description="Send it back when changing the budget; 0 = no budget yet.")
    received: Decimal = Field(description="Sum of client payments.")
    spent: Decimal = Field(description="Sum of spending.")
    remaining: Decimal | None = Field(description="Budget minus spent; negative = over budget.")
    balance: Decimal = Field(description="Received minus spent.")
    spent_percent: int | None = Field(description="Spent as a share of the budget, rounded.")
    over_budget: bool


class FinanceEntryOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: FinanceEntryKind
    amount: Decimal
    entry_date: date
    description: str
    created_by: uuid.UUID
    created_at: datetime


class FinanceEntryListOut(BaseModel):
    items: list[FinanceEntryOut]
    total: int
    page: int
    page_size: int
