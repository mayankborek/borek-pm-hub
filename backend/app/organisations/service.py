"""Organisations and their account managers. Routers check permissions; rules live here."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.auth.permissions import account_manager_condition
from app.common.enums import OrganisationType
from app.common.validation import like_escape
from app.core.errors import AppError
from app.organisations.models import Organisation, OrganisationAccountManager
from app.organisations.schemas import (
    OrganisationCreate,
    OrganisationOut,
    OrganisationUpdate,
    PersonBrief,
)
from app.projects.models import Project
from app.users.models import User


def _not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Organisation not found.")


def _duplicate_name() -> AppError:
    return AppError(409, "DUPLICATE_ORGANISATION", "An organisation with this name already exists.")


def _version_conflict() -> AppError:
    return AppError(
        409,
        "VERSION_CONFLICT",
        "The organisation was changed by someone else. Reload and try again.",
    )


async def get_organisation(session: AsyncSession, organisation_id: uuid.UUID) -> Organisation:
    organisation = await session.get(Organisation, organisation_id)
    if organisation is None:
        raise _not_found()
    return organisation


async def _name_taken(
    session: AsyncSession, name: str, *, except_id: uuid.UUID | None = None
) -> bool:
    query = select(Organisation.id).where(func.lower(Organisation.name) == name.lower())
    if except_id is not None:
        query = query.where(Organisation.id != except_id)
    return await session.scalar(query) is not None


async def account_managers(
    session: AsyncSession, organisation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[PersonBrief]]:
    found: dict[uuid.UUID, list[PersonBrief]] = defaultdict(list)
    if not organisation_ids:
        return found
    rows = await session.execute(
        select(OrganisationAccountManager.organisation_id, User)
        .join(User, User.id == OrganisationAccountManager.user_id)
        .where(OrganisationAccountManager.organisation_id.in_(organisation_ids))
        .order_by(User.name, User.id)
    )
    for organisation_id, user in rows.all():
        found[organisation_id].append(PersonBrief(id=user.id, name=user.name, email=user.email))
    return found


async def to_out(session: AsyncSession, organisations: list[Organisation]) -> list[OrganisationOut]:
    managers = await account_managers(session, [o.id for o in organisations])
    return [
        OrganisationOut(
            id=o.id,
            name=o.name,
            type=o.type,
            archived_at=o.archived_at,
            version=o.version,
            created_at=o.created_at,
            account_managers=managers[o.id],
        )
        for o in organisations
    ]


async def list_organisations(
    session: AsyncSession,
    *,
    q: str | None,
    organisation_type: OrganisationType | None,
    include_archived: bool,
    page: int,
    page_size: int,
) -> tuple[list[Organisation], int]:
    conditions: list[ColumnElement[bool]] = []
    if not include_archived:
        conditions.append(Organisation.archived_at.is_(None))
    if organisation_type:
        conditions.append(Organisation.type == organisation_type.value)
    if q and q.strip():
        conditions.append(Organisation.name.ilike(f"%{like_escape(q.strip())}%", escape="\\"))
    total = await session.scalar(select(func.count(Organisation.id)).where(*conditions)) or 0
    rows = await session.scalars(
        select(Organisation)
        .where(*conditions)
        .order_by(Organisation.name, Organisation.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


async def create_organisation(
    session: AsyncSession, actor: User, data: OrganisationCreate
) -> Organisation:
    if await _name_taken(session, data.name):
        raise _duplicate_name()
    organisation = Organisation(name=data.name, type=data.type.value)
    session.add(organisation)
    try:
        await session.flush()  # a concurrent insert of the same name fails here
    except IntegrityError:
        await session.rollback()
        raise _duplicate_name() from None
    record_audit(
        session,
        actor,
        "organisation.created",
        "organisation",
        organisation.id,
        after={"name": data.name, "type": data.type.value},
    )
    await session.commit()
    await session.refresh(organisation)
    return organisation


async def update_organisation(
    session: AsyncSession, actor: User, organisation_id: uuid.UUID, data: OrganisationUpdate
) -> Organisation:
    organisation = await get_organisation(session, organisation_id)
    if data.version != organisation.version:
        raise _version_conflict()
    if organisation.archived_at is not None:
        raise AppError(409, "ORGANISATION_ARCHIVED", "The organisation is archived.")
    if data.name == organisation.name:
        return organisation
    if await _name_taken(session, data.name, except_id=organisation.id):
        raise _duplicate_name()
    before = {"name": organisation.name}
    organisation.name = data.name
    record_audit(
        session,
        actor,
        "organisation.updated",
        "organisation",
        organisation.id,
        before=before,
        after={"name": data.name},
    )
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise _version_conflict() from None
    except IntegrityError:
        await session.rollback()
        raise _duplicate_name() from None
    await session.refresh(organisation)
    return organisation


async def archive_organisation(
    session: AsyncSession, actor: User, organisation_id: uuid.UUID
) -> None:
    """Hide it from lists. Refused while active users or projects still belong to it. Archiving
    twice is harmless."""
    organisation = await get_organisation(session, organisation_id)
    if organisation.archived_at is not None:
        return
    users = await session.scalar(
        select(func.count(User.id)).where(
            User.organisation_id == organisation.id, User.is_active.is_(True)
        )
    )
    projects = await session.scalar(
        select(func.count(Project.id)).where(
            Project.client_organisation_id == organisation.id, Project.archived_at.is_(None)
        )
    )
    if users or projects:
        raise AppError(
            409,
            "ORGANISATION_IN_USE",
            "Active users or projects still belong to this organisation.",
        )
    organisation.archived_at = datetime.now(UTC)
    record_audit(session, actor, "organisation.archived", "organisation", organisation.id)
    await session.commit()


async def set_account_managers(
    session: AsyncSession, actor: User, organisation_id: uuid.UUID, user_ids: list[uuid.UUID]
) -> list[PersonBrief]:
    """Replace who manages this client. Only active Account Managers, only client organisations."""
    organisation = await get_organisation(session, organisation_id)
    if organisation.archived_at is not None:
        raise AppError(409, "ORGANISATION_ARCHIVED", "The organisation is archived.")
    if organisation.type != OrganisationType.CLIENT.value:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Account managers can only be assigned to client organisations.",
        )
    wanted = set(user_ids)
    valid = set(
        await session.scalars(
            select(User.id).where(
                User.id.in_(wanted), User.is_active.is_(True), account_manager_condition()
            )
        )
    )
    invalid = wanted - valid
    if invalid:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Some users do not exist, are inactive or are not Account Managers.",
            [
                {"field": "user_ids", "issue": "not_account_manager", "message": str(user_id)}
                for user_id in sorted(invalid, key=str)
            ],
        )
    rows = await session.execute(
        select(OrganisationAccountManager.user_id)
        .where(OrganisationAccountManager.organisation_id == organisation.id)
        .with_for_update()
    )
    current = set(rows.scalars())
    if wanted != current:
        await session.execute(
            delete(OrganisationAccountManager).where(
                OrganisationAccountManager.organisation_id == organisation.id,
                OrganisationAccountManager.user_id.in_(current - wanted),
            )
        )
        session.add_all(
            OrganisationAccountManager(
                organisation_id=organisation.id, user_id=user_id, granted_by=actor.id
            )
            for user_id in wanted - current
        )
        record_audit(
            session,
            actor,
            "organisation.account_managers_changed",
            "organisation",
            organisation.id,
            before={"user_ids": sorted(str(i) for i in current)},
            after={"user_ids": sorted(str(i) for i in wanted)},
        )
        try:
            await session.commit()
        except IntegrityError:  # someone else assigned the same person at the same moment
            await session.rollback()
            raise AppError(
                409, "CONFLICT", "The list was changed by someone else. Reload and try again."
            ) from None
    return (await account_managers(session, [organisation.id]))[organisation.id]
