import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.validation import check_date, clean_optional_text, clean_text
from app.organisations.schemas import PersonBrief

MAX_TEXT = 20_000


class PhaseStatus(StrEnum):
    """Shown under the phase name on the roadmap."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class MilestoneState(StrEnum):
    """Worked out when read (first match wins): done, late, revised, at_risk, in_progress,
    planned."""

    DONE = "done"  # the PM marked it reached
    LATE = "late"  # due date passed and not done ("Running late")
    REVISED = "revised"  # an approved change request moved the due date
    AT_RISK = "at_risk"  # the PM's warning flag
    IN_PROGRESS = "in_progress"  # a linked task has started, or its phase has started
    PLANNED = "planned"


def _name(value: str) -> str:
    return clean_text(value, label="Name")


def _long(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=MAX_TEXT, label="Text")


def _date(value: date | None) -> date | None:
    return check_date(value, "date")


def _not_null(model: BaseModel, fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in model.model_fields_set and getattr(model, field) is None:
            raise ValueError(f"{field} must not be null.")


# --- phases -------------------------------------------------------------------------------------


class PhaseCreate(BaseModel):
    """A new phase goes to the end of the roadmap (reorder with PUT /phases/order)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200)
    description: str | None = None
    start_date: date
    end_date: date
    client_visible: bool = Field(default=False, description="Shown on the client's roadmap.")

    _clean_name = field_validator("name")(_name)
    _clean_long = field_validator("description")(_long)
    _clean_dates = field_validator("start_date", "end_date")(_date)

    @model_validator(mode="after")
    def _order(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date.")
        return self


class PhaseUpdate(BaseModel):
    """Send `version` plus only the fields that change."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    client_visible: bool | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        return None if value is None else _name(value)

    _clean_long = field_validator("description")(_long)
    _clean_dates = field_validator("start_date", "end_date")(_date)

    @model_validator(mode="after")
    def _required(self) -> Self:
        _not_null(self, ("name", "start_date", "end_date", "client_visible"))
        return self


class PhaseOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_ids: list[uuid.UUID] = Field(
        max_length=200, description="Every active phase of the project, in the new order."
    )


class PhaseOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    start_date: date
    end_date: date
    position: int
    client_visible: bool
    status: PhaseStatus
    is_late: bool = Field(description="End date passed and the phase is not completed.")
    progress: int | None = Field(
        description="Completed share, 0-100: done tasks of the phase's milestones; without "
        "linked tasks, the share of its milestones that are done; 100 once completed. Null = "
        "not available (no milestones yet)."
    )
    milestones_total: int
    milestones_done: int
    version: int
    created_at: datetime
    updated_at: datetime


# --- milestones ---------------------------------------------------------------------------------


class MilestoneCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200)
    due_date: date
    phase_id: uuid.UUID | None = Field(
        default=None, description="Optional; a phase of the project."
    )
    owner_id: uuid.UUID | None = Field(default=None, description="A member of the project.")
    description: str | None = None
    completion_criteria: str | None = None
    at_risk: bool = False
    client_visible: bool = Field(default=False, description="Shown on the client's roadmap.")

    _clean_name = field_validator("name")(_name)
    _clean_long = field_validator("description", "completion_criteria")(_long)
    _clean_date = field_validator("due_date")(_date)


class MilestoneUpdate(BaseModel):
    """Send `version` plus only the fields that change. `done: true` marks the milestone
    reached (by you, now); `done: false` opens it again. Null clears an optional field."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    phase_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    description: str | None = None
    completion_criteria: str | None = None
    at_risk: bool | None = None
    client_visible: bool | None = None
    done: bool | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        return None if value is None else _name(value)

    _clean_long = field_validator("description", "completion_criteria")(_long)
    _clean_date = field_validator("due_date")(_date)

    @model_validator(mode="after")
    def _required(self) -> Self:
        _not_null(self, ("name", "due_date", "at_risk", "client_visible", "done"))
        return self


class MilestoneOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    phase_id: uuid.UUID | None
    code: str = Field(description="M-01, M-02 ... per project.")
    name: str
    description: str | None
    completion_criteria: str | None
    due_date: date = Field(description="The current due date (after any approved change).")
    original_due_date: date | None = Field(
        description="The date before an approved change request moved it (state revised)."
    )
    requested_date: date | None = Field(
        description="A new date asked for by a change request still in review."
    )
    change_request_code: str | None = Field(
        description="The open request asking for `requested_date`, else the approved one that "
        "moved the date."
    )
    owner: PersonBrief | None
    state: MilestoneState
    done: bool
    completed_at: datetime | None
    completed_by: PersonBrief | None
    at_risk: bool
    client_visible: bool
    progress: int | None = Field(
        description="Done linked tasks / linked tasks, 0-100; 100 once done. Null = not "
        "available (no linked tasks and not done): never show it as 0%."
    )
    tasks_total: int
    tasks_done: int
    version: int
    created_at: datetime
    updated_at: datetime


class LinkedTaskOut(BaseModel):
    id: uuid.UUID
    key: str
    title: str
    status_name: str
    status_category: str
    assignee: PersonBrief | None
    due_date: date | None


class MilestoneDetailOut(MilestoneOut):
    tasks: list[LinkedTaskOut] = Field(description="Linked tasks (not archived), by key.")


# --- roadmap ------------------------------------------------------------------------------------


class RoadmapPhaseOut(PhaseOut):
    milestones: list[MilestoneOut] = Field(description="By due date.")


class RoadmapOut(BaseModel):
    """Everything the roadmap screen draws, in one call."""

    project_id: uuid.UUID
    today: date
    range_start: date | None = Field(
        description="Earliest of project start, phase starts and milestone dates."
    )
    range_end: date | None = Field(
        description="Latest of project target end, phase ends and milestone dates."
    )
    phases: list[RoadmapPhaseOut] = Field(description="In roadmap order.")
    unphased_milestones: list[MilestoneOut] = Field(
        description="Milestones not in any phase, by due date."
    )
