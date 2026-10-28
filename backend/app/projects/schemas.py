"""Request and response shapes for the project endpoints."""

import re
import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import ProjectRole, ProjectStatus
from app.common.validation import check_date, clean_optional_text, clean_text

_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,19}$", re.ASCII)
MAX_DESCRIPTION = 20_000
MAX_MEMBERS = 200


def _clean_description(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=MAX_DESCRIPTION, label="Description")


def _check_start(value: date | None) -> date | None:
    return check_date(value, "start_date")


def _check_end(value: date | None) -> date | None:
    return check_date(value, "target_end_date")


class MemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    project_role: ProjectRole = ProjectRole.DEVELOPER


class MemberRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_role: ProjectRole


class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    project_role: ProjectRole
    granted_at: datetime


class TaskSummary(BaseModel):
    """Task counts for list cards, overview and dashboard.

    Archived tasks are not counted. Overdue = due before today (UTC) and not in a done
    status. The counts follow the status categories (done / in_progress / blocked).
    `completion_percent` is completed / total, rounded, 0 when there are no tasks.
    """

    total: int = 0
    completed: int = 0
    in_progress: int = 0
    blocked: int = 0
    overdue: int = 0
    completion_percent: int = 0


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        max_length=40, description="Unique short identifier, 2-20 chars (A-Z, 0-9, _ -). Immutable."
    )
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: ProjectStatus = ProjectStatus.PLANNED
    start_date: date | None = None
    target_end_date: date | None = None
    members: list[MemberIn] = Field(default_factory=list, max_length=MAX_MEMBERS)

    _clean_desc = field_validator("description")(_clean_description)
    _range_start = field_validator("start_date")(_check_start)
    _range_end = field_validator("target_end_date")(_check_end)

    @field_validator("code")
    @classmethod
    def _normalise_code(cls, value: str) -> str:
        value = value.strip()
        if not _CODE_PATTERN.fullmatch(value):
            raise ValueError("Use 2-20 characters: letters, digits, '_' or '-'.")
        return value.upper()

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        return clean_text(value, label="Name")

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if self.start_date and self.target_end_date and self.target_end_date < self.start_date:
            raise ValueError("target_end_date must not be before start_date.")
        return self


class ProjectUpdate(BaseModel):
    """PATCH body. `code` is not accepted (immutable). Send only the fields that change."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, description="Version from the last read (optimistic locking).")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: ProjectStatus | None = None
    start_date: date | None = None
    target_end_date: date | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(value, label="Name")

    _clean_desc = field_validator("description")(_clean_description)
    _range_start = field_validator("start_date")(_check_start)
    _range_end = field_validator("target_end_date")(_check_end)


class ProjectOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    status: ProjectStatus
    start_date: date | None
    target_end_date: date | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    version: int
    task_summary: TaskSummary


class ProjectDetailOut(ProjectOut):
    members: list[MemberOut]


class ProjectListOut(BaseModel):
    items: list[ProjectOut]
    total: int
    page: int
    page_size: int
