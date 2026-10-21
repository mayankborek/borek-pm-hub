"""Response shapes for the PM and developer dashboards (F06, F07)."""

import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.projects.schemas import TaskSummary
from app.tasks.schemas import TaskOut, UserBrief


class MemberCounts(BaseModel):
    user: UserBrief
    project_role: str
    tasks: TaskSummary = Field(description="Tasks assigned to this member in the project.")


class ProjectCard(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: str
    start_date: date | None
    target_end_date: date | None
    tasks: TaskSummary
    members: list[MemberCounts] = Field(
        default_factory=list, description="Per-member counts; only filled on the developer view."
    )


class AttentionList(BaseModel):
    """The first `limit` tasks that need action; `total` is the full count."""

    total: int
    items: list[TaskOut]


class PmDashboard(BaseModel):
    """All active projects. Archived projects and tasks are not counted."""

    active_projects: int = Field(description="Projects with status 'active'.")
    projects_total: int = Field(description="Non-archived projects, any status.")
    summary: TaskSummary
    projects: list[ProjectCard]
    blocked: AttentionList = Field(description="Longest without an update first.")
    overdue: AttentionList = Field(description="Oldest due date first.")


class MyDashboard(BaseModel):
    """The signed-in user's tasks and projects (developer landing data)."""

    summary: TaskSummary = Field(description="Tasks assigned to me.")
    projects: list[ProjectCard] = Field(description="My projects, with per-member counts.")
    blocked: AttentionList
    overdue: AttentionList
