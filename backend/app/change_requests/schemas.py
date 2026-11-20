import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.change_requests.models import ChangeRequestStatus
from app.common.validation import check_date, clean_optional_text, clean_text
from app.organisations.schemas import PersonBrief

MAX_TEXT = 20_000


def _title(value: str) -> str:
    return clean_text(value, label="Title")


def _description(value: str) -> str:
    value = clean_text(value, label="Description", multiline=True)
    if len(value) > MAX_TEXT:
        raise ValueError(f"Description can be at most {MAX_TEXT} characters.")
    return value


def _long(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=MAX_TEXT, label="Text")


def _date(value: date | None) -> date | None:
    return check_date(value, "requested_date")


class ChangeRequestCreate(BaseModel):
    """Raise a request. To move a milestone, send it with the new date you want."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=200)
    description: str
    reason: str | None = None
    milestone_id: uuid.UUID | None = Field(default=None, description="The milestone it affects.")
    requested_date: date | None = Field(
        default=None, description="New due date for the milestone; needs milestone_id."
    )

    _clean_title = field_validator("title")(_title)
    _clean_description = field_validator("description")(_description)
    _clean_reason = field_validator("reason")(_long)
    _clean_date = field_validator("requested_date")(_date)

    @model_validator(mode="after")
    def _date_needs_milestone(self) -> Self:
        if self.requested_date is not None and self.milestone_id is None:
            raise ValueError("requested_date needs milestone_id.")
        return self


class ChangeRequestVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)


class ChangeRequestUpdate(BaseModel):
    """Project lead or Manager, while the request is open (pending or in review): correct it
    and fill in the impact. Send `version` plus only the fields that change; null clears an
    optional field."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    reason: str | None = None
    milestone_id: uuid.UUID | None = None
    requested_date: date | None = None
    impact_schedule_days: int | None = Field(
        default=None, ge=-3650, le=3650, description="Days the delivery moves (minus = earlier)."
    )
    impact_effort_hours: int | None = Field(default=None, ge=0, le=100_000)
    impact_scope: str | None = None

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str | None) -> str | None:
        return None if value is None else _title(value)

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str | None) -> str | None:
        return None if value is None else _description(value)

    _clean_long = field_validator("reason", "impact_scope")(_long)
    _clean_date = field_validator("requested_date")(_date)

    @model_validator(mode="after")
    def _required(self) -> Self:
        for field in ("title", "description"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null.")
        return self


class ChangeRequestDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    decision: Literal["approved", "declined"]
    note: str | None = Field(default=None, description="Why; shown to the client too.")

    _clean_note = field_validator("note")(_long)


class MilestoneBrief(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    due_date: date


class ChangeRequestOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str = Field(description="CR-01, CR-02 ... per project.")
    title: str
    description: str
    reason: str | None
    milestone: MilestoneBrief | None
    requested_date: date | None
    status: ChangeRequestStatus
    review_started_at: datetime | None
    impact_schedule_days: int | None
    impact_effort_hours: int | None
    impact_scope: str | None
    decision_note: str | None
    decided_by: PersonBrief | None
    decided_at: datetime | None
    submitted_by: PersonBrief
    submitted_by_client: bool = Field(description="Raised by a client contact.")
    version: int
    created_at: datetime
    updated_at: datetime


class ChangeRequestListOut(BaseModel):
    items: list[ChangeRequestOut]
    total: int
    counts: dict[str, int] = Field(
        description="Requests per status (pending, in_review, approved, declined) and `total`, "
        "unfiltered."
    )


MAX_COMMENT = 10_000


def _comment_body(value: str) -> str:
    value = clean_text(value, label="Comment", multiline=True)
    if len(value) > MAX_COMMENT:
        raise ValueError(f"A comment can be at most {MAX_COMMENT} characters.")
    return value


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str
    internal: bool = Field(
        default=False,
        description="Staff only: a note for the project team that the client never sees.",
    )

    _clean_body = field_validator("body")(_comment_body)


class ClientCommentCreate(BaseModel):
    """A client's message: always part of the shared conversation."""

    model_config = ConfigDict(extra="forbid")

    body: str

    _clean_body = field_validator("body")(_comment_body)


class CommentOut(BaseModel):
    id: uuid.UUID
    body: str
    internal: bool
    author: PersonBrief
    author_is_client: bool
    created_at: datetime


class AttachmentOut(BaseModel):
    id: uuid.UUID
    name: str
    content_type: str
    size_bytes: int
    uploaded_by: PersonBrief
    created_at: datetime
