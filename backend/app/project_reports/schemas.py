import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.validation import check_date, clean_optional_text, clean_text
from app.organisations.schemas import PersonBrief
from app.project_reports.models import Audience, PeriodKind, ReportKind

MAX_PERIOD_DAYS = 3 * 366


# --- content (the snapshot) -------------------------------------------------------------------


class Kpi(BaseModel):
    key: str = Field(description="Stable id, e.g. total, completed, remaining, completion.")
    label: str
    value: str = Field(description="Ready to show (numbers as text, percent with %).")


class DistributionItem(BaseModel):
    label: str = Field(description="Status name.")
    category: str | None = Field(description="Status category (todo, done ...) for colours.")
    count: int


class Fact(BaseModel):
    key: str = Field(description="Stable id, e.g. status, health, target, pm, next_action.")
    label: str
    value: str


class Table(BaseModel):
    key: str = Field(description="Stable id, e.g. tasks, milestones, change_requests.")
    heading: str
    columns: list[str]
    rows: list[list[str]] = Field(description="Cells as text; dates ISO (YYYY-MM-DD).")
    total_rows: int = Field(description="Rows before the cut at MAX_ROWS.")


class ReportContent(BaseModel):
    """What the report shows, generic so the preview and the PDF render every type the same
    way: KPI tiles, a status distribution, label/value facts and tables."""

    kpis: list[Kpi] = []
    distribution: list[DistributionItem] = []
    facts: list[Fact] = []
    tables: list[Table] = []


# --- input ------------------------------------------------------------------------------------


def _title(value: str | None) -> str | None:
    return None if value is None else clean_text(value, label="title")


class ReportSettings(BaseModel):
    """Generate (POST) and Edit (PUT, same fields + version). Periods:
    - tasks, milestones, change_requests: `custom` with period_start and period_end;
    - project_status: `overall` (no dates) or `weekly` (period_start = any day of the week;
      saved as that Monday to Sunday);
    - other: `overall`; `title` and `summary` (the expert summary) are required."""

    model_config = ConfigDict(extra="forbid")

    kind: ReportKind
    period_kind: PeriodKind | None = Field(
        default=None, description="Left out: custom, overall for project_status and other."
    )
    period_start: date | None = None
    period_end: date | None = None
    title: str | None = Field(
        default=None, max_length=200, description="Left out: a title for the type."
    )
    summary: str | None = Field(default=None, description="The expert summary (free text).")

    _clean_title = field_validator("title")(_title)

    @field_validator("period_start", "period_end")
    @classmethod
    def _clean_date(cls, value: date | None) -> date | None:
        return check_date(value, "The date")

    @field_validator("summary")
    @classmethod
    def _clean_summary(cls, value: str | None) -> str | None:
        return clean_optional_text(value, max_length=20_000, label="summary")

    @model_validator(mode="after")
    def _period(self) -> Self:
        default = (
            PeriodKind.OVERALL
            if self.kind in (ReportKind.PROJECT_STATUS, ReportKind.OTHER)
            else PeriodKind.CUSTOM
        )
        kind = self.period_kind or default
        self.period_kind = kind
        allowed = {
            ReportKind.PROJECT_STATUS: {PeriodKind.OVERALL, PeriodKind.WEEKLY},
            ReportKind.OTHER: {PeriodKind.OVERALL},
        }.get(self.kind, {PeriodKind.CUSTOM})
        if kind not in allowed:
            raise ValueError(
                f"period_kind for {self.kind.value}: "
                + ", ".join(sorted(k.value for k in allowed))
                + "."
            )
        if kind == PeriodKind.OVERALL:
            if self.period_start or self.period_end:
                raise ValueError("An overall report has no dates.")
        elif kind == PeriodKind.WEEKLY:
            if self.period_start is None:
                raise ValueError("A weekly report needs period_start (a day of the week).")
            monday = date.fromordinal(self.period_start.toordinal() - self.period_start.weekday())
            self.period_start = monday
            self.period_end = date.fromordinal(monday.toordinal() + 6)
        else:
            if self.period_start is None or self.period_end is None:
                raise ValueError("period_start and period_end are required.")
            if self.period_end < self.period_start:
                raise ValueError("period_end must not be before period_start.")
            if (self.period_end - self.period_start).days > MAX_PERIOD_DAYS:
                raise ValueError("The reporting period can be at most 3 years.")
        if self.kind == ReportKind.OTHER and (not self.title or not self.summary):
            raise ValueError("A report of type other needs a title and a summary.")
        return self


class ReportEdit(ReportSettings):
    version: int = Field(ge=1)


class ReportShare(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    audiences: list[Audience] = Field(
        max_length=3,
        description="Who can view it: the full list (replaces the previous one; [] = nobody).",
    )


# --- output -----------------------------------------------------------------------------------


class ReportBrief(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: ReportKind
    title: str
    period_kind: PeriodKind
    period_start: date | None
    period_end: date | None
    prepared_by: PersonBrief
    generated_at: datetime
    shared_with: list[Audience]
    shared_at: datetime | None = Field(description="Last time the audiences were changed.")
    shared_by: PersonBrief | None
    version: int
    created_at: datetime
    updated_at: datetime


class ReportOut(ReportBrief):
    project_name: str
    project_code: str
    client_name: str | None
    summary: str | None
    content: ReportContent


class ReportListOut(BaseModel):
    items: list[ReportBrief]
    total: int
    page: int
    page_size: int


class ClientReportBrief(BaseModel):
    id: uuid.UUID
    kind: ReportKind
    title: str
    period_kind: PeriodKind
    period_start: date | None
    period_end: date | None
    prepared_by: str = Field(description="Name.")
    shared_at: datetime | None


class ClientReportDetail(ClientReportBrief):
    project_name: str
    client_name: str | None
    summary: str | None
    content: ReportContent
    generated_at: datetime


class ClientReportListOut(BaseModel):
    items: list[ClientReportBrief]
    total: int
