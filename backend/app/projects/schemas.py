"""Request and response shapes for the project endpoints."""

import re
import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import ProjectRole, ProjectStatus, ProjectType, TaskPriority
from app.common.validation import check_date, clean_optional_text, clean_text
from app.organisations.schemas import (
    MemberInviteOut,
    OrganisationBrief,
    OrganisationMemberCreate,
    OrganisationMemberOut,
)

_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,19}$", re.ASCII)
MAX_DESCRIPTION = 20_000
MAX_MEMBERS = 200


def _clean_description(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=MAX_DESCRIPTION, label="Description")


def _check_start(value: date | None) -> date | None:
    return check_date(value, "start_date")


def _check_end(value: date | None) -> date | None:
    return check_date(value, "target_end_date")


MAX_CATEGORY = 100


def _clean_category(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=MAX_CATEGORY, label="Category", multiline=False)


class NewClientIn(BaseModel):
    """A client organisation made together with an external project, with its first contact."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200, description="Name of the new client organisation.")
    contact: OrganisationMemberCreate | None = Field(
        default=None, description="First contact: gets a client account and an invite link."
    )

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return clean_text(value, label="Name")


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
    type: ProjectType = ProjectType.INTERNAL
    category: str | None = Field(default=None, max_length=MAX_CATEGORY)
    priority: TaskPriority = TaskPriority.MEDIUM
    client_organisation_id: uuid.UUID | None = Field(
        default=None, description="An existing client (external projects only)."
    )
    new_client: NewClientIn | None = Field(
        default=None,
        description="Or a new client, made in the same step (external projects only).",
    )
    members: list[MemberIn] = Field(default_factory=list, max_length=MAX_MEMBERS)

    _clean_desc = field_validator("description")(_clean_description)
    _clean_cat = field_validator("category")(_clean_category)
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

    @model_validator(mode="after")
    def _check_client(self) -> Self:
        has_existing = self.client_organisation_id is not None
        has_new = self.new_client is not None
        if self.type == ProjectType.EXTERNAL and has_existing == has_new:
            raise ValueError(
                "An external project needs a client: send client_organisation_id or new_client."
            )
        if self.type == ProjectType.INTERNAL and (has_existing or has_new):
            raise ValueError("An internal project has no client organisation.")
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
    type: ProjectType | None = None
    category: str | None = Field(
        default=None, max_length=MAX_CATEGORY, description='null or "" clears it.'
    )
    priority: TaskPriority | None = None
    client_organisation_id: uuid.UUID | None = Field(
        default=None,
        description="The customer; null removes it. External projects must keep one, "
        "internal ones cannot have one (change `type` in the same request).",
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(value, label="Name")

    _clean_desc = field_validator("description")(_clean_description)
    _range_start = field_validator("start_date")(_check_start)
    _range_end = field_validator("target_end_date")(_check_end)
    _clean_cat = field_validator("category")(_clean_category)


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
    archived_by: uuid.UUID | None
    type: ProjectType
    category: str | None
    priority: TaskPriority
    client_organisation: OrganisationBrief | None
    version: int
    task_summary: TaskSummary


class ProjectDetailOut(ProjectOut):
    members: list[MemberOut]


class ClientContactCreatedOut(BaseModel):
    member: OrganisationMemberOut
    invite: MemberInviteOut


class ProjectCreatedOut(ProjectDetailOut):
    client_contact: ClientContactCreatedOut | None = Field(
        default=None,
        description="Only when `new_client.contact` was sent: hand `invite.url` to the person "
        "(shown once, no email is sent yet).",
    )


class CategoryOut(BaseModel):
    name: str
    project_count: int


class ProjectListOut(BaseModel):
    items: list[ProjectOut]
    total: int
    page: int
    page_size: int
