"""Request and response shapes for the status and task endpoints."""

import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import StatusCategory, TaskPriority

MAX_LABELS = 10


# --- statuses ---------------------------------------------------------------------------------


def _clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Name is required.")
    return value


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
    category: str


class StatusOut(StatusBrief):
    position: int
    task_count: int = Field(description="Tasks in this status, archived ones excluded.")


# --- tasks ------------------------------------------------------------------------------------


def _clean_labels(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        label = value.strip()
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
    value = value.strip()
    if not value:
        raise ValueError("Title is required.")
    return value


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
    progress: int = Field(default=0, ge=0, le=100)
    assignee_id: uuid.UUID | None = Field(
        default=None, description="Developers can only assign tasks to themselves."
    )
    blocked_reason: str | None = None

    _strip_title = field_validator("title")(_clean_title)
    _clean = field_validator("labels")(_clean_labels)

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValueError("due_date must not be before start_date.")
        return self


class TaskUpdate(BaseModel):
    """PATCH body. Send `version` plus only the fields that change.

    PMs may change everything. Developers may change `status_id`, `progress` and
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
    progress: int | None = Field(default=None, ge=0, le=100)
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
    project_code: str
    project_name: str
    title: str
    description: str | None
    status: StatusBrief
    priority: str
    labels: list[str]
    start_date: date | None
    due_date: date | None
    progress: int
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
