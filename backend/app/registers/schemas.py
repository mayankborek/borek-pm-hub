import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import TaskPriority
from app.common.validation import check_date, clean_optional_text, clean_text
from app.organisations.schemas import PersonBrief
from app.registers.models import Level, RegisterKind

MAX_TEXT = 20_000

# Fields that belong to one kind only.
KIND_FIELDS: dict[RegisterKind, frozenset[str]] = {
    RegisterKind.RISK: frozenset({"probability", "impact", "mitigation"}),
    RegisterKind.ISSUE: frozenset({"priority"}),
    RegisterKind.DECISION: frozenset({"decided_on", "decided_by", "rationale"}),
}


def _long(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=MAX_TEXT, label="Text")


def _short(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=200, label="Text", multiline=False)


def _date(value: date | None) -> date | None:
    return check_date(value, "date")


class RegisterFields(BaseModel):
    """Common: description, status, owner (a project member), due date. Risks: probability,
    impact, mitigation. Issues: priority. Decisions: decided_on, decided_by, rationale. Fields of
    another kind are refused (422)."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    status: str | None = Field(
        default=None,
        description="Risk: open, mitigating, closed. Issue: open, in_progress, resolved, closed. "
        "Decision: proposed, decided, superseded. Default: the first.",
    )
    owner_id: uuid.UUID | None = None
    due_date: date | None = None
    probability: Level | None = None
    impact: Level | None = None
    mitigation: str | None = None
    priority: TaskPriority | None = None
    decided_on: date | None = None
    decided_by: str | None = Field(default=None, max_length=200, description="Name or body.")
    rationale: str | None = None

    _clean_long = field_validator("description", "mitigation", "rationale")(_long)
    _clean_short = field_validator("decided_by")(_short)
    _clean_dates = field_validator("due_date", "decided_on")(_date)


class RegisterCreate(RegisterFields):
    title: str = Field(max_length=200)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return clean_text(value, label="Title")


class RegisterUpdate(RegisterFields):
    """Send `version` plus only the fields that change; null clears an optional field."""

    version: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=200)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(value, label="Title")

    @model_validator(mode="after")
    def _not_null(self) -> "RegisterUpdate":
        for field in ("title", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null.")
        return self


class RegisterItemOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: RegisterKind
    code: str
    title: str
    description: str | None
    status: str
    owner: PersonBrief | None
    due_date: date | None
    overdue: bool = Field(description="Due date passed and not closed / resolved / decided.")
    probability: Level | None
    impact: Level | None
    score: int | None = Field(description="Risks: probability x impact, 1 (low/low) to 9.")
    mitigation: str | None
    priority: TaskPriority | None
    decided_on: date | None
    decided_by: str | None
    rationale: str | None
    created_by: PersonBrief
    created_at: datetime
    updated_at: datetime
    version: int


class RegisterListOut(BaseModel):
    items: list[RegisterItemOut]
    total: int
    counts: dict[str, int] = Field(description="Per status, over all items of this kind.")
