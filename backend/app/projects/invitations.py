"""Project invitations (PM design spec + RD-12 People & Access, Mayank 25.11.2026).

A project lead (or a Manager) invites people from the project itself:
- **team**: a new internal person (developer or PM) gets an account without a password, joins
  the project and gets an invite link;
- **client**: a new contact of the project's client organisation (external projects) gets a
  `client` account and an invite link (client access is per organisation).

Then, for anyone listed in the project's People & Access: **resend** (a new link; the old one
stops working), **revoke** (the open link stops working, the person stays listed) and
**remove** (team: leaves the project; client contact: the account is deactivated, as in
/organisations/{id}/members). There is no mail yet, so the link goes back to the caller.
Invite state (invited / invite_expired) stays separate from access (active / deactivated).
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.audit.service import record_audit
from app.auth.invites import issue_invite
from app.auth.permissions import is_client
from app.common.enums import GlobalRole, OrganisationType, ProjectRole
from app.common.validation import clean_email
from app.core.config import Settings
from app.core.errors import AppError
from app.organisations import members as organisation_members
from app.organisations.models import Organisation
from app.organisations.schemas import (
    MemberInviteOut,
    OrganisationMemberCreate,
    OrganisationMemberOut,
    clean_job_title,
)
from app.projects import service as project_service
from app.projects.models import Project, ProjectMember
from app.users.models import User, UserInvite


class ProjectInviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["team", "client"] = Field(
        description="team: a new internal person joins this project; client: a new contact of "
        "the project's client organisation (external projects only)."
    )
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(max_length=320)
    job_title: str | None = Field(default=None, max_length=100)
    role: Literal["developer", "pm"] = Field(
        default="developer", description="team only: the new person's role in the hub."
    )
    project_role: ProjectRole = Field(
        default=ProjectRole.DEVELOPER,
        description="team only. project_lead needs role pm.",
    )

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("The name cannot be empty.")
        return cleaned

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return clean_email(value)

    _job_title = field_validator("job_title")(clean_job_title)


class ProjectInviteOut(BaseModel):
    person: OrganisationMemberOut
    kind: Literal["team", "client"]
    invite: MemberInviteOut


def _invalid(field: str, issue: str, message: str) -> AppError:
    return AppError(
        422,
        "VALIDATION_ERROR",
        "The request is not valid.",
        [{"field": field, "issue": issue, "message": message}],
    )


def _not_listed() -> AppError:
    return AppError(404, "NOT_FOUND", "This person is not part of the project.")


async def _client_organisation(session: AsyncSession, project: Project) -> Organisation:
    if project.project_type != "external" or project.client_organisation_id is None:
        raise AppError(
            409,
            "NO_CLIENT_ORGANISATION",
            "Only external projects with a client organisation have client contacts.",
        )
    organisation = await session.get(Organisation, project.client_organisation_id)
    if (
        organisation is None
        or organisation.type != OrganisationType.CLIENT.value
        or organisation.archived_at is not None
    ):
        raise AppError(409, "NO_CLIENT_ORGANISATION", "The client organisation is not available.")
    return organisation


async def _email_taken(session: AsyncSession, email: str) -> None:
    taken = await session.scalar(select(User.id).where(func.lower(User.email) == email))
    if taken is not None:
        raise AppError(
            409,
            "EMAIL_TAKEN",
            "A user with this email already exists. Add an existing person as a project member.",
        )


async def invite(
    session: AsyncSession, actor: User, project: Project, data: ProjectInviteIn, settings: Settings
) -> tuple[User, str, datetime]:
    """Create the account (+ membership for team) and its first invite link. Commits."""
    if data.kind == "client":
        organisation = await _client_organisation(session, project)
        user, token, expires_at = await organisation_members.insert_member(
            session,
            actor,
            organisation,
            OrganisationMemberCreate(name=data.name, email=data.email, job_title=data.job_title),
            settings,
        )
    else:
        if data.project_role == ProjectRole.PROJECT_LEAD and data.role != "pm":
            raise _invalid("project_role", "needs_pm", "Only a PM can lead a project.")
        await _email_taken(session, data.email)
        user = User(
            name=data.name,
            email=data.email,
            global_role=GlobalRole(data.role).value,
            organisation_id=None if is_client(actor) else actor.organisation_id,
            job_title=data.job_title,
        )
        session.add(user)
        await session.flush()
        token, expires_at = await issue_invite(session, user, actor, settings)
        session.add(
            ProjectMember(
                project_id=project.id,
                user_id=user.id,
                project_role=data.project_role.value,
                granted_by=actor.id,
            )
        )
        record_audit(
            session,
            actor,
            "user.created",
            "user",
            user.id,
            project_id=project.id,
            after={"name": user.name, "email": user.email, "role": user.global_role},
        )
        record_audit(
            session,
            actor,
            "member.added",
            "user",
            user.id,
            project_id=project.id,
            after={"project_role": data.project_role.value},
        )
    await session.commit()
    return user, token, expires_at


async def _listed(
    session: AsyncSession, project: Project, user_id: uuid.UUID
) -> tuple[User, Literal["team", "client"]]:
    """A project member, or a client contact of the project's client (external projects).
    Account Managers are assigned by the administrator and are not handled here."""
    user = await session.get(User, user_id)
    if user is None:
        raise _not_listed()
    member = await session.scalar(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user_id
        )
    )
    if member is not None:
        return user, "team"
    if (
        is_client(user)
        and project.project_type == "external"
        and project.client_organisation_id is not None
        and user.organisation_id == project.client_organisation_id
    ):
        return user, "client"
    raise _not_listed()


def _already_joined() -> AppError:
    return AppError(409, "ALREADY_JOINED", "This person has already set a password and signed in.")


async def resend(
    session: AsyncSession, actor: User, project: Project, user_id: uuid.UUID, settings: Settings
) -> tuple[User, Literal["team", "client"], str, datetime]:
    """A new link for someone who has not joined yet; older unused links stop working."""
    user, kind = await _listed(session, project, user_id)
    if user.password_hash is not None:
        raise _already_joined()
    user, token, expires_at = await admin_service.new_invite(session, actor, user.id, settings)
    return user, kind, token, expires_at


async def revoke(session: AsyncSession, actor: User, project: Project, user_id: uuid.UUID) -> User:
    """The open link stops working; the person stays listed (status invite_expired) and can
    get a new link with resend. Harmless when no link is open. Commits."""
    user, _ = await _listed(session, project, user_id)
    if user.password_hash is not None:
        raise _already_joined()
    result = await session.execute(
        update(UserInvite)
        .where(
            UserInvite.user_id == user.id,
            UserInvite.used_at.is_(None),
            UserInvite.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    if getattr(result, "rowcount", 0):
        record_audit(session, actor, "user.invite_revoked", "user", user.id, project_id=project.id)
    await session.commit()
    return user


async def remove(session: AsyncSession, actor: User, project: Project, user_id: uuid.UUID) -> None:
    """Team: leaves the project (their tasks here become unassigned). Client contact: the
    account is deactivated (client access is per organisation, so it ends on every project of
    that client). Commits."""
    user, kind = await _listed(session, project, user_id)
    if kind == "team":
        await project_service.remove_member(session, project.id, user.id, actor)
        return
    assert project.client_organisation_id is not None
    await organisation_members.remove_member(
        session, actor, project.client_organisation_id, user.id
    )
