import re
import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import RagStatus, ReportState, StakeholderInfluence
from app.common.validation import check_date, clean_email, clean_optional_text, clean_text
from app.organisations.schemas import PersonBrief

MAX_TEXT = 20_000
_PHONE = re.compile(r"^[0-9+()\-./ ]{3,50}$")


def _long_text(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=MAX_TEXT, label="Text")


def _short_text(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=200, label="Text", multiline=False)


def _summary(value: str) -> str:
    value = clean_text(value, label="Summary", multiline=True)
    if len(value) > MAX_TEXT:
        raise ValueError(f"Summary can be at most {MAX_TEXT} characters.")
    return value


def _report_date(value: date | None) -> date | None:
    return check_date(value, "report_date")


class StatusReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rag: RagStatus
    summary: str
    achievements: str | None = None
    next_steps: str | None = None
    risks: str | None = None
    report_date: date | None = Field(default=None, description="Empty: today.")

    _clean_summary = field_validator("summary")(_summary)
    _clean_long = field_validator("achievements", "next_steps", "risks")(_long_text)
    _clean_date = field_validator("report_date")(_report_date)


class StatusReportUpdate(BaseModel):
    """Only drafts can change. Send only the fields that change."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    rag: RagStatus | None = None
    summary: str | None = None
    achievements: str | None = None
    next_steps: str | None = None
    risks: str | None = None
    report_date: date | None = None

    @field_validator("summary")
    @classmethod
    def _clean_summary(cls, value: str | None) -> str | None:
        return None if value is None else _summary(value)

    _clean_long = field_validator("achievements", "next_steps", "risks")(_long_text)
    _clean_date = field_validator("report_date")(_report_date)

    @model_validator(mode="after")
    def _required_not_null(self) -> Self:
        for field in ("rag", "summary", "report_date"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null.")
        return self


class StatusReportOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    rag: RagStatus
    summary: str
    achievements: str | None
    next_steps: str | None
    risks: str | None
    report_date: date
    state: ReportState
    published_at: datetime | None
    published_by: PersonBrief | None
    author: PersonBrief
    version: int
    created_at: datetime
    updated_at: datetime


class StatusReportListOut(BaseModel):
    items: list[StatusReportOut]
    total: int
    page: int
    page_size: int


class StakeholderFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organisation: str | None = None
    role_title: str | None = None
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    influence: StakeholderInfluence | None = None
    notes: str | None = None

    _clean_short = field_validator("organisation", "role_title")(_short_text)
    _clean_notes = field_validator("notes")(_long_text)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return clean_email(value) if value and value.strip() else None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not _PHONE.fullmatch(value):
            raise ValueError("Use digits, spaces and + ( ) - . / in a phone number.")
        return value


class StakeholderCreate(StakeholderFields):
    name: str = Field(max_length=200)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return clean_text(value, label="Name")


class StakeholderUpdate(StakeholderFields):
    """Send only the fields that change; null clears an optional field."""

    version: int = Field(ge=1)
    name: str | None = Field(default=None, max_length=200)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(value, label="Name")

    @model_validator(mode="after")
    def _name_not_null(self) -> Self:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null.")
        return self


class StakeholderOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    organisation: str | None
    role_title: str | None
    email: str | None
    phone: str | None
    influence: StakeholderInfluence | None
    notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime
