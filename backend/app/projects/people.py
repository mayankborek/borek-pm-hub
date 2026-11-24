"""People & Access (BB-22, RD-12): everyone around one project in one call.

The project team (members with their project role), the client's Account Managers and the
client contacts (external projects), each with their sign-in status (invited, invite expired,
active, deactivated) and what the reader may do about it. The changes themselves use the routes
that already exist: project members (`/projects/{id}/members`) and client contacts
(`/organisations/{id}/members`, incl. a new invite link)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.admin.schemas import AdminUserOut
from app.auth.permissions import Action, client_condition
from app.common.enums import ProjectRole
from app.organisations.members import _status
from app.organisations.models import OrganisationAccountManager
from app.organisations.schemas import MemberStatus
from app.projects.models import Project, ProjectMember
from app.projects.service import allowed_in
from app.users.models import User


class Person(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str = Field(description="Global role (pm, developer, manager, account_manager, client).")
    job_title: str | None
    status: MemberStatus = Field(
        description="invited / invite_expired (no password yet), active, deactivated."
    )


class TeamMember(Person):
    project_role: ProjectRole
    granted_at: datetime


class AccountManager(Person):
    assigned_at: datetime


class ClientContact(Person):
    join_date: date | None


class PeopleActions(BaseModel):
    manage_team: bool = Field(description="Add / remove members, change project roles.")
    manage_client_contacts: bool = Field(
        description="Add / remove client contacts and create new invite links (administrator)."
    )


class ProjectPeopleOut(BaseModel):
    project_id: uuid.UUID
    team: list[TeamMember]
    account_managers: list[AccountManager]
    client_contacts: list[ClientContact] = Field(description="Empty for internal projects.")
    counts: dict[str, int] = Field(description="Per status over everyone listed.")
    can: PeopleActions


def _person(out: AdminUserOut) -> dict[str, Any]:
    return {
        "id": out.id,
        "name": out.name,
        "email": out.email,
        "role": out.role,
        "job_title": out.job_title,
        "status": _status(out),
    }


async def project_people(session: AsyncSession, user: User, project: Project) -> ProjectPeopleOut:
    members = list(
        (
            await session.execute(
                select(ProjectMember, User)
                .join(User, User.id == ProjectMember.user_id)
                .where(ProjectMember.project_id == project.id)
                .order_by(User.name, User.email)
            )
        ).all()
    )
    managers: list[Any] = []
    contacts: list[User] = []
    if project.client_organisation_id:
        managers = list(
            (
                await session.execute(
                    select(OrganisationAccountManager, User)
                    .join(User, User.id == OrganisationAccountManager.user_id)
                    .where(
                        OrganisationAccountManager.organisation_id == project.client_organisation_id
                    )
                    .order_by(User.name)
                )
            ).all()
        )
        if project.project_type == "external":
            contacts = list(
                await session.scalars(
                    select(User)
                    .where(
                        User.organisation_id == project.client_organisation_id, client_condition()
                    )
                    .order_by(User.name, User.email)
                )
            )
    everyone = [u for _, u in members] + [u for _, u in managers] + contacts
    outs = {
        o.id: o
        for o in await admin_service.to_out(session, list({u.id: u for u in everyone}.values()))
    }
    team = [
        TeamMember(
            **_person(outs[u.id]),
            project_role=ProjectRole(m.project_role),
            granted_at=m.granted_at,
        )
        for m, u in members
    ]
    ams = [
        AccountManager(**_person(outs[u.id]), assigned_at=link.granted_at) for link, u in managers
    ]
    client = [ClientContact(**_person(outs[u.id]), join_date=u.join_date) for u in contacts]
    counts: dict[str, int] = {}
    for p in [*team, *ams, *client]:
        counts[p.status] = counts.get(p.status, 0) + 1
    return ProjectPeopleOut(
        project_id=project.id,
        team=team,
        account_managers=ams,
        client_contacts=client,
        counts=counts,
        can=PeopleActions(
            manage_team=await allowed_in(session, user, project, Action.MEMBER_MANAGE),
            manage_client_contacts=await allowed_in(
                session, user, project, Action.ORGANISATION_MANAGE
            ),
        ),
    )
