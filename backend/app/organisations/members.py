"""Members (contacts) of a client organisation, administrator only.

Adding a member creates a `client` account without a password and its invite link in one step
(there is no mail yet, so the link goes back to the administrator, who passes it on). Removing a
member deactivates the account: nothing is deleted and the person stays listed as deactivated.
Only client organisations have members here; internal people are managed in /admin/users.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.admin.schemas import AdminUserOut
from app.audit.service import record_audit
from app.auth.invites import issue_invite
from app.auth.permissions import CLIENT_CONTACT_ROLE, is_client
from app.common.enums import OrganisationType
from app.core.config import Settings
from app.core.errors import AppError
from app.organisations import service as organisation_service
from app.organisations.models import Organisation
from app.organisations.schemas import (
    MemberStatus,
    OrganisationCreate,
    OrganisationMemberCreate,
    OrganisationMemberOut,
)
from app.organisations.service import get_organisation
from app.users.models import User


def _status(user: AdminUserOut) -> MemberStatus:
    if not user.is_active:
        return "deactivated"
    if user.password_set:
        return "active"
    return "invited" if user.invite_pending else "invite_expired"


async def to_out(session: AsyncSession, users: list[User]) -> list[OrganisationMemberOut]:
    return [
        OrganisationMemberOut(
            id=u.id,
            name=u.name,
            email=u.email,
            role=u.role,
            status=_status(u),
            is_active=u.is_active,
            password_set=u.password_set,
            invite_pending=u.invite_pending,
            job_title=u.job_title,
            join_date=u.join_date,
            created_at=u.created_at,
        )
        for u in await admin_service.to_out(session, users)
    ]


def _not_a_member() -> AppError:
    return AppError(404, "NOT_FOUND", "Member not found.")


async def _client_organisation(
    session: AsyncSession, organisation_id: uuid.UUID, *, for_change: bool
) -> Organisation:
    """The organisation, refused when it is internal (or archived, for changes)."""
    organisation = await get_organisation(session, organisation_id)
    if organisation.type != OrganisationType.CLIENT.value:
        raise AppError(
            409,
            "NOT_A_CLIENT_ORGANISATION",
            "Only client organisations have members here. Manage internal people in Users.",
        )
    if for_change and organisation.archived_at is not None:
        raise AppError(409, "ORGANISATION_ARCHIVED", "This organisation is archived.")
    return organisation


async def _member(session: AsyncSession, organisation: Organisation, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None or user.organisation_id != organisation.id:
        raise _not_a_member()
    return user


async def list_members(
    session: AsyncSession, organisation_id: uuid.UUID, *, page: int, page_size: int
) -> tuple[list[User], int]:
    """Everyone whose account belongs to the organisation, deactivated people included."""
    organisation = await _client_organisation(session, organisation_id, for_change=False)
    condition = User.organisation_id == organisation.id
    total = await session.scalar(select(func.count(User.id)).where(condition)) or 0
    rows = await session.scalars(
        select(User)
        .where(condition)
        .order_by(User.is_active.desc(), User.name, User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


async def add_member(
    session: AsyncSession,
    actor: User,
    organisation_id: uuid.UUID,
    data: OrganisationMemberCreate,
    settings: Settings,
) -> tuple[User, str, datetime]:
    """Create the client account and its first invite link. Commits."""
    organisation = await _client_organisation(session, organisation_id, for_change=True)
    user, token, expires_at = await insert_member(session, actor, organisation, data, settings)
    await session.commit()
    return user, token, expires_at


async def insert_member(
    session: AsyncSession,
    actor: User,
    organisation: Organisation,
    data: OrganisationMemberCreate,
    settings: Settings,
) -> tuple[User, str, datetime]:
    """Add the client account, its invite link and the audit entry without committing."""
    taken = await session.scalar(select(User.id).where(func.lower(User.email) == data.email))
    if taken is not None:
        raise AppError(409, "EMAIL_TAKEN", "A user with this email already exists.")
    user = User(
        name=data.name,
        email=data.email,
        global_role=CLIENT_CONTACT_ROLE.value,
        organisation_id=organisation.id,
        job_title=data.job_title,
    )
    session.add(user)
    await session.flush()
    token, expires_at = await issue_invite(session, user, actor, settings)
    record_audit(
        session,
        actor,
        "organisation.member_added",
        "organisation",
        organisation.id,
        after={"user_id": str(user.id), "name": user.name, "email": user.email},
    )
    return user, token, expires_at


async def renew_invite(
    session: AsyncSession,
    actor: User,
    organisation_id: uuid.UUID,
    user_id: uuid.UUID,
    settings: Settings,
) -> tuple[User, str, datetime]:
    """A fresh link, for example when the first one expired; older unused links stop working."""
    organisation = await _client_organisation(session, organisation_id, for_change=True)
    user = await _member(session, organisation, user_id)
    return await admin_service.new_invite(session, actor, user.id, settings)


async def remove_member(
    session: AsyncSession, actor: User, organisation_id: uuid.UUID, user_id: uuid.UUID
) -> User:
    """Deactivate the account (sign-in stops at once). It stays in the organisation, so it can
    be activated again in /admin/users. Doing it twice changes nothing. Commits."""
    organisation = await _client_organisation(session, organisation_id, for_change=False)
    user = await _member(session, organisation, user_id)
    if not is_client(user):
        raise AppError(
            409,
            "NOT_A_CLIENT_CONTACT",
            "This person is not a client contact. Change the account in Users.",
        )
    if user.is_active:
        await refuse_last_contact(session, user)
        record_audit(
            session,
            actor,
            "organisation.member_removed",
            "organisation",
            organisation.id,
            before={"user_id": str(user.id), "name": user.name, "email": user.email},
        )
    await admin_service.set_active(session, actor, user.id, active=False)
    return user


async def refuse_last_contact(session: AsyncSession, user: User) -> None:
    """409 when the person is the last named contact of an active project (handoff 08)."""
    projects = await organisation_service.projects_left_without_contact(session, user)
    if projects:
        names = ", ".join(p.name for p in projects)
        raise AppError(
            409,
            "LAST_PROJECT_CONTACT",
            f"Assign another contact to {names} before removing {user.name}.",
            [
                {"field": "project_id", "issue": "last_contact", "message": str(p.id)}
                for p in projects
            ],
        )


async def create_organisation(
    session: AsyncSession, actor: User, data: OrganisationCreate, settings: Settings
) -> tuple[Organisation, list[tuple[User, str, datetime]]]:
    """The whole setup in one transaction: organisation, details, Account Managers, optional
    PM and the first client accounts with invite links. Commits."""
    emails = [c.email for c in data.contacts]
    duplicates = sorted({e for e in emails if emails.count(e) > 1})
    if duplicates:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Each contact email can be used once.",
            [{"field": "contacts", "issue": "duplicate_email", "message": e} for e in duplicates],
        )
    if data.contacts and data.type != OrganisationType.CLIENT:
        raise AppError(
            422, "VALIDATION_ERROR", "Only client organisations have client contacts here."
        )
    async with session.begin_nested():  # any refusal undoes the whole setup
        organisation = await organisation_service.insert_organisation(session, actor, data)
        created = [
            await insert_member(session, actor, organisation, contact, settings)
            for contact in data.contacts
        ]
    try:
        await session.commit()
    except IntegrityError:  # the same name or email saved by someone else at the same moment
        await session.rollback()
        raise AppError(
            409, "CONFLICT", "Something was saved by someone else. Reload and try again."
        ) from None
    await session.refresh(organisation)
    return organisation, created
