"""Request and response shapes for the project endpoints."""

import re
import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import ProjectRole, ProjectStatus

_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,19}$")


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
    project_role: str
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

    code: str = Field(description="Unique short identifier, 2-20 chars (A-Z, 0-9, _ -). Immutable.")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: ProjectStatus = ProjectStatus.PLANNED
    start_date: date | None = None
    target_end_date: date | None = None
    members: list[MemberIn] = Field(default_factory=list)

    @field_validator("code")
    @classmethod
    def _normalise_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not _CODE_PATTERN.match(value):
            raise ValueError("Use 2-20 characters: letters, digits, '_' or '-'.")
        return value

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required.")
        return value

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
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Name is required.")
        return value


class ProjectOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    status: str
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
