"""Membership lookups used by auth. Other modules call these instead of touching the tables."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.projects.models import Project, ProjectMember


@dataclass(frozen=True)
class Membership:
    project_id: uuid.UUID
    project_code: str
    project_name: str
    project_role: str


async def list_memberships(session: AsyncSession, user_id: uuid.UUID) -> list[Membership]:
    """The user's projects, excluding archived ones."""
    rows = await session.execute(
        select(Project.id, Project.code, Project.name, ProjectMember.project_role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user_id, Project.archived_at.is_(None))
        .order_by(Project.code)
    )
    return [Membership(*row) for row in rows.all()]


async def is_member(session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> bool:
    row = await session.execute(
        select(ProjectMember.id)
        .join(Project, Project.id == ProjectMember.project_id)
        .where(
            ProjectMember.user_id == user_id,
            ProjectMember.project_id == project_id,
            Project.archived_at.is_(None),
        )
    )
    return row.first() is not None
