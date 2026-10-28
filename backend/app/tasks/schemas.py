"""Request and response shapes for the status and task endpoints."""

import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import EstimateUnit, StatusCategory, TaskPriority
from app.common.validation import check_date, clean_optional_text, clean_text

MAX_LABELS = 10
MAX_LABEL_INPUT = 50  # raw list size accepted before de-duplication
MAX_ESTIMATE = 1_000_000
MAX_DESCRIPTION = 20_000
MAX_BLOCKED_REASON = 1_000
MAX_ESTIMATE_BY_UNIT = {
    EstimateUnit.MINUTES: 100_000,
    EstimateUnit.HOURS: 10_000,
    EstimateUnit.WEEKS: 520,
}


# --- statuses ---------------------------------------------------------------------------------


def _clean_name(value: str) -> str:
    return clean_text(value, label="Name")


class StatusCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=50)
    category: StatusCategory

    _strip = field_validator("name")(_clean_name)


class StatusUpdate(BaseModel):
    """PATCH body: send only what changes."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=50)
    category: StatusCategory | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)


class StatusOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_ids: list[uuid.UUID] = Field(description="Every status of the project, in new order.")


class StatusBrief(BaseModel):
    id: uuid.UUID
    name: str
    category: StatusCategory


class StatusOut(StatusBrief):
    position: int
    task_count: int = Field(description="Tasks in this status, archived ones excluded.")


# --- tasks ------------------------------------------------------------------------------------


def _clean_labels(values: list[str]) -> list[str]:
    if len(values) > MAX_LABEL_INPUT:
        raise ValueError(f"A task can have at most {MAX_LABELS} labels.")
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        label = clean_text(value, label="A label") if value.strip() else ""
        if not label:
            raise ValueError("Labels must not be empty.")
        if len(label) > 30:
            raise ValueError("A label can have at most 30 characters.")
        if label.lower() not in seen:
            seen.add(label.lower())
            cleaned.append(label)
    if len(cleaned) > MAX_LABELS:
        raise ValueError(f"A task can have at most {MAX_LABELS} labels.")
    return cleaned


def _clean_title(value: str) -> str:
    return clean_text(value, label="Title")


def _clean_description(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=MAX_DESCRIPTION, label="Description")


def _clean_reason(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=MAX_BLOCKED_REASON, label="Blocked reason")


def _check_estimate(value: int | None, unit: EstimateUnit | None) -> None:
    if (value is None) != (unit is None):
        raise ValueError("estimate_value and estimate_unit must be sent together.")
    if value is not None and unit is not None and value > MAX_ESTIMATE_BY_UNIT[unit]:
        raise ValueError(
            f"estimate_value can be at most {MAX_ESTIMATE_BY_UNIT[unit]} {unit.value}."
        )


def _check_start(value: date | None) -> date | None:
    return check_date(value, "start_date")


def _check_due(value: date | None) -> date | None:
    return check_date(value, "due_date")


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    status_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the first 'todo' status of the project."
    )
    priority: TaskPriority = TaskPriority.MEDIUM
    labels: list[str] = Field(default_factory=list)
    start_date: date | None = None
    due_date: date | None = Field(default=None, description="Date the task should be completed.")
    estimate_value: int | None = Field(
        default=None, gt=0, le=MAX_ESTIMATE, description="Whole amount; needs estimate_unit."
    )
    estimate_unit: EstimateUnit | None = Field(
        default=None, description="minutes, hours or weeks; needs estimate_value."
    )
    assignee_id: uuid.UUID | None = Field(
        default=None, description="Developers can only assign tasks to themselves."
    )
    blocked_reason: str | None = None

    _strip_title = field_validator("title")(_clean_title)
    _clean = field_validator("labels")(_clean_labels)
    _clean_desc = field_validator("description")(_clean_description)
    _clean_blocked = field_validator("blocked_reason")(_clean_reason)
    _range_start = field_validator("start_date")(_check_start)
    _range_due = field_validator("due_date")(_check_due)

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValueError("due_date must not be before start_date.")
        _check_estimate(self.estimate_value, self.estimate_unit)
        return self


class TaskUpdate(BaseModel):
    """PATCH body. Send `version` plus only the fields that change.

    PMs may change everything. Developers may change `status_id` and
    `blocked_reason` on tasks assigned to them, nothing else.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, description="Version from the last read (optimistic locking).")
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status_id: uuid.UUID | None = None
    priority: TaskPriority | None = None
    labels: list[str] | None = None
    start_date: date | None = None
    due_date: date | None = None
    estimate_value: int | None = Field(default=None, gt=0, le=MAX_ESTIMATE)
    estimate_unit: EstimateUnit | None = None
    assignee_id: uuid.UUID | None = None
    blocked_reason: str | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        return None if value is None else _clean_title(value)

    @field_validator("labels")
    @classmethod
    def _clean(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _clean_labels(value)

    @field_validator("title", "priority", "labels", "status_id", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("This field cannot be empty.")
        return value

    _clean_desc = field_validator("description")(_clean_description)
    _clean_blocked = field_validator("blocked_reason")(_clean_reason)
    _range_start = field_validator("start_date")(_check_start)
    _range_due = field_validator("due_date")(_check_due)

    @model_validator(mode="after")
    def _check_pair(self) -> Self:
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValueError("due_date must not be before start_date.")
        if self.estimate_value is not None and self.estimate_unit is not None:
            _check_estimate(self.estimate_value, self.estimate_unit)
        return self


class AssigneeUpdate(BaseModel):
    """PUT body for assigning a task. `assignee_id: null` unassigns it."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, description="Version from the last read (optimistic locking).")
    assignee_id: uuid.UUID | None


class UserBrief(BaseModel):
    id: uuid.UUID
    name: str
    email: str


class TaskOut(BaseModel):
    id: uuid.UUID
    key: str
    project_id: uuid.UUID
    project_name: str
    title: str
    description: str | None
    status: StatusBrief
    priority: TaskPriority
    labels: list[str]
    start_date: date | None
    due_date: date | None
    estimate_value: int | None
    estimate_unit: str | None
    assignee: UserBrief | None
    reporter: UserBrief
    blocked_reason: str | None
    blocked_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    version: int


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int


class BoardColumn(BaseModel):
    status: StatusOut
    total: int
    tasks: list[TaskOut]


class BoardOut(BaseModel):
    """Kanban data: one column per project status, in the project's order."""

    columns: list[BoardColumn]
    total: int


TaskSort = Literal[
    "created_at",
    "-created_at",
    "updated_at",
    "-updated_at",
    "due_date",
    "-due_date",
    "priority",
    "-priority",
]
