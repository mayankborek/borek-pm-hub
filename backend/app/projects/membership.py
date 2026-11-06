"""Membership lookups used by auth. Other modules call these instead of touching the tables."""

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import (
    Resource,
    has_lead_rights,
    is_account_manager,
    may_lead_projects,
)
from app.common.enums import ProjectRole
from app.organisations.models import OrganisationAccountManager
from app.projects.models import Project, ProjectMember
from app.users.models import User


@dataclass(frozen=True)
class ProjectAccess:
    """What the user is in this project, as `can()` needs it."""

    is_member: bool = False
    is_project_lead: bool = False
    is_account_manager: bool = False

    def resource(
        self,
        project_id: uuid.UUID,
        *,
        assignee_id: uuid.UUID | None = None,
        creator_id: uuid.UUID | None = None,
    ) -> Resource:
        return Resource(
            project_id=project_id,
            is_member=self.is_member,
            is_project_lead=self.is_project_lead,
            is_account_manager=self.is_account_manager,
            assignee_id=assignee_id,
            creator_id=creator_id,
        )


def assigned_clients(user: User) -> Select[tuple[uuid.UUID]]:
    """The client organisations assigned to this Account Manager."""
    return select(OrganisationAccountManager.organisation_id).where(
        OrganisationAccountManager.user_id == user.id
    )


def visible_project_ids(user: User) -> Select[tuple[uuid.UUID]]:
    """Active projects the user reaches without seeing everything: an Account Manager those of
    their clients, everyone else the ones they are a member of."""
    if is_account_manager(user):
        return select(Project.id).where(
            Project.client_organisation_id.in_(assigned_clients(user)),
            Project.archived_at.is_(None),
        )
    return (
        select(ProjectMember.project_id)
        .join(Project, Project.id == ProjectMember.project_id)
        .where(ProjectMember.user_id == user.id, Project.archived_at.is_(None))
    )


async def project_access(session: AsyncSession, user: User, project: Project) -> ProjectAccess:
    """Membership counts in active projects. An archived project stays visible (read-only: every
    write refuses it) only to a PM who led it or archived it. An Account Manager reaches the
    active projects of their clients."""
    if is_account_manager(user):
        if project.archived_at is not None or project.client_organisation_id is None:
            return ProjectAccess()
        assigned = await session.scalar(
            select(OrganisationAccountManager.id).where(
                OrganisationAccountManager.user_id == user.id,
                OrganisationAccountManager.organisation_id == project.client_organisation_id,
            )
        )
        return ProjectAccess(is_account_manager=assigned is not None)
    role = await session.scalar(
        select(ProjectMember.project_role).where(
            ProjectMember.user_id == user.id, ProjectMember.project_id == project.id
        )
    )
    is_lead = role == ProjectRole.PROJECT_LEAD.value
    if project.archived_at is None:
        return ProjectAccess(is_member=role is not None, is_project_lead=is_lead)
    if may_lead_projects(user) and (is_lead or project.archived_by == user.id):
        return ProjectAccess(is_member=True, is_project_lead=True)
    return ProjectAccess()


async def lead_rights_in(session: AsyncSession, user: User, project_id: uuid.UUID) -> bool:
    """Whether the user may do the lead's work in this project."""
    project = await session.get(Project, project_id)
    if project is None:
        return False
    access = await project_access(session, user, project)
    return has_lead_rights(user, is_project_lead=access.is_project_lead)


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


async def project_role(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> str | None:
    """The user's role in an active project, or None when they are not a member."""
    return await session.scalar(
        select(ProjectMember.project_role)
        .join(Project, Project.id == ProjectMember.project_id)
        .where(
            ProjectMember.user_id == user_id,
            ProjectMember.project_id == project_id,
            Project.archived_at.is_(None),
        )
    )
