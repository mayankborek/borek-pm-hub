import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.validation import clean_optional_text, clean_text
from app.organisations.schemas import PersonBrief
from app.requirements.models import AcceptanceDecision, RequirementStatus

MAX_TEXT = 20_000
MAX_CRITERIA = 50
MAX_CRITERION = 1_000

# draft: not published yet. awaiting_answer: with the client now. answered: the client answered
# it. superseded: a newer version was published before the client answered this one.
VersionState = Literal["draft", "awaiting_answer", "answered", "superseded"]


def _title(value: str) -> str:
    return clean_text(value, label="Title")


def _description(value: str) -> str:
    value = clean_text(value, label="Description", multiline=True)
    if len(value) > MAX_TEXT:
        raise ValueError(f"Description can be at most {MAX_TEXT} characters.")
    return value


def _long(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=MAX_TEXT, label="Text")


def _criteria(values: list[str] | None) -> list[str] | None:
    """Trimmed, blank lines dropped, duplicates removed (first spelling kept), order kept."""
    if values is None:
        return None
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = value.strip()
        if not value:
            continue
        value = clean_text(value, label="Acceptance criterion", multiline=True)
        if len(value) > MAX_CRITERION:
            raise ValueError(f"An acceptance criterion can be at most {MAX_CRITERION} characters.")
        if value.casefold() not in seen:
            seen.add(value.casefold())
            out.append(value)
    if len(out) > MAX_CRITERIA:
        raise ValueError(f"At most {MAX_CRITERIA} acceptance criteria.")
    return out


class RequirementCreate(BaseModel):
    """Starts as a draft with version 1. Publish it to send it to the client for acceptance."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=200)
    description: str
    acceptance_criteria: list[str] = Field(
        default_factory=list, description="What the client checks; at least one to publish."
    )
    owner_id: uuid.UUID | None = Field(default=None, description="An active project member.")
    milestone_id: uuid.UUID | None = Field(default=None, description="The milestone it belongs to.")

    _clean_title = field_validator("title")(_title)
    _clean_description = field_validator("description")(_description)

    @field_validator("acceptance_criteria")
    @classmethod
    def _clean_criteria(cls, value: list[str]) -> list[str]:
        cleaned = _criteria(value)
        assert cleaned is not None
        return cleaned


class RequirementUpdate(BaseModel):
    """Send `version` plus only the fields that change; null clears owner or milestone.

    title, owner and milestone change the requirement itself. description, acceptance_criteria
    and change_note are the content: they change the draft version, or, when the newest version
    is already published, start a new draft version (the client keeps seeing the published one
    until the new one is published). Not possible once accepted or rejected."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=200)
    owner_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = None
    description: str | None = None
    acceptance_criteria: list[str] | None = None
    change_note: str | None = Field(
        default=None, description="What changed since the last version; shown to the client."
    )

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str | None) -> str | None:
        return None if value is None else _title(value)

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str | None) -> str | None:
        return None if value is None else _description(value)

    _clean_criteria = field_validator("acceptance_criteria")(_criteria)
    _clean_note = field_validator("change_note")(_long)

    @model_validator(mode="after")
    def _required(self) -> Self:
        for field in ("title", "description", "acceptance_criteria"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null.")
        return self


class RequirementVersionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)


class MilestoneBrief(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    due_date: date


class RequirementVersionOut(BaseModel):
    number: int
    state: VersionState
    description: str
    acceptance_criteria: list[str]
    change_note: str | None
    created_by: PersonBrief
    created_at: datetime
    published_at: datetime | None
    published_by: PersonBrief | None
    response: AcceptanceDecision | None
    response_comment: str | None
    responded_by: PersonBrief | None
    responded_at: datetime | None


class RequirementOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str = Field(description="REQ-01, REQ-02 ... per project.")
    title: str
    owner: PersonBrief | None
    milestone: MilestoneBrief | None
    status: RequirementStatus
    current_version: int = Field(description="Number of the newest version (draft or not).")
    published_version: int | None = Field(
        description="Number of the newest published version, the one the client sees."
    )
    has_unpublished_changes: bool = Field(
        description="The newest version is a draft and an older version was published."
    )
    versions: list[RequirementVersionOut] = Field(description="Newest first.")
    created_by: PersonBrief
    version: int = Field(description="For optimistic locking (not the content version).")
    created_at: datetime
    updated_at: datetime


class RequirementListOut(BaseModel):
    items: list[RequirementOut]
    total: int
    counts: dict[str, int] = Field(
        description="Requirements per status and `total`, unfiltered (acceptance tracking)."
    )


# --- client side ----------------------------------------------------------------------------------


class ClientRequirementResponse(BaseModel):
    """The client's answer to the version they reviewed. A comment is required unless they
    accept."""

    model_config = ConfigDict(extra="forbid")

    version_number: int = Field(ge=1, description="The published version the client reviewed.")
    decision: AcceptanceDecision
    comment: str | None = None

    _clean_comment = field_validator("comment")(_long)

    @model_validator(mode="after")
    def _comment_needed(self) -> Self:
        if self.decision is not AcceptanceDecision.ACCEPTED and self.comment is None:
            raise ValueError("Say what should change, or why it is rejected, in comment.")
        return self


class ClientRequirementVersionOut(BaseModel):
    number: int
    state: Literal["awaiting_answer", "answered", "superseded"]
    description: str
    acceptance_criteria: list[str]
    change_note: str | None
    published_at: datetime
    published_by: str | None = Field(description="Name of the person who published it.")
    response: AcceptanceDecision | None
    response_comment: str | None
    responded_by: str | None = Field(description="Name of the client contact who answered.")
    responded_at: datetime | None


class ClientMilestoneLink(BaseModel):
    code: str
    name: str


class ClientRequirementOut(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    status: RequirementStatus = Field(description="Never draft: drafts never reach the client.")
    awaiting_your_answer: bool = Field(
        description="True when the current version waits for the client's answer."
    )
    owner: str | None = Field(description="Name of the requirement's owner.")
    milestone: ClientMilestoneLink | None = Field(description="Only if shown to the client.")
    current: ClientRequirementVersionOut = Field(description="The newest published version.")
    history: list[ClientRequirementVersionOut] = Field(
        description="Earlier published versions, newest first."
    )


class ClientRequirementListOut(BaseModel):
    items: list[ClientRequirementOut] = Field(description="By code.")
    counts: dict[str, int] = Field(
        description="Requirements per status (awaiting_acceptance, changes_requested, accepted, "
        "rejected) and `total`."
    )
