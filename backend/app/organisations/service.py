"""Organisations and their account managers. Routers check permissions; rules live here."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.auth.permissions import account_manager_condition, client_condition, pm_condition
from app.common.enums import OrganisationType
from app.common.validation import like_escape
from app.core.errors import AppError
from app.organisations.models import Organisation, OrganisationAccountManager
from app.organisations.schemas import (
    OrganisationCreate,
    OrganisationOut,
    OrganisationProject,
    OrganisationUpdate,
    PersonBrief,
)
from app.projects.models import Project, ProjectClientContact
from app.users.models import User

# Details an administrator sets on the organisation (handoff 07/08).
DETAILS = ("industry", "website", "primary_contact_email", "project_manager_id")


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


def _brief(user: User) -> PersonBrief:
    return PersonBrief(id=user.id, name=user.name, email=user.email)


async def _projects(
    session: AsyncSession, organisation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[OrganisationProject]]:
    """Active projects per organisation with their named contacts (active client accounts of
    that organisation only, so a contact never shows on another client's project)."""
    found: dict[uuid.UUID, list[OrganisationProject]] = defaultdict(list)
    if not organisation_ids:
        return found
    projects = list(
        await session.scalars(
            select(Project)
            .where(
                Project.client_organisation_id.in_(organisation_ids),
                Project.archived_at.is_(None),
            )
            .order_by(Project.code)
        )
    )
    contacts: dict[uuid.UUID, list[PersonBrief]] = defaultdict(list)
    if projects:
        rows = await session.execute(
            select(ProjectClientContact.project_id, User)
            .join(User, User.id == ProjectClientContact.user_id)
            .join(Project, Project.id == ProjectClientContact.project_id)
            .where(
                ProjectClientContact.project_id.in_([p.id for p in projects]),
                User.is_active.is_(True),
                User.organisation_id == Project.client_organisation_id,
            )
            .order_by(User.name, User.id)
        )
        for project_id, user in rows.all():
            contacts[project_id].append(_brief(user))
    for p in projects:
        assert p.client_organisation_id is not None
        found[p.client_organisation_id].append(
            OrganisationProject(
                id=p.id,
                code=p.code,
                name=p.name,
                contacts=contacts[p.id],
                needs_contact=not contacts[p.id],
            )
        )
    return found


async def to_out(session: AsyncSession, organisations: list[Organisation]) -> list[OrganisationOut]:
    ids = [o.id for o in organisations]
    managers = await account_managers(session, ids)
    projects = await _projects(session, ids)
    pm_ids = {o.project_manager_id for o in organisations if o.project_manager_id}
    pms = (
        {
            u.id: _brief(u)
            for u in (await session.scalars(select(User).where(User.id.in_(pm_ids)))).all()
        }
        if pm_ids
        else {}
    )
    counts: dict[uuid.UUID, int] = {}
    if ids:
        rows = await session.execute(
            select(User.organisation_id, func.count(User.id))
            .where(User.organisation_id.in_(ids), User.is_active.is_(True), client_condition())
            .group_by(User.organisation_id)
        )
        counts = {org_id: count for org_id, count in rows.all() if org_id is not None}
    return [
        OrganisationOut(
            id=o.id,
            name=o.name,
            type=o.type,
            archived_at=o.archived_at,
            version=o.version,
            created_at=o.created_at,
            account_managers=managers[o.id],
            industry=o.industry,
            website=o.website,
            primary_contact_email=o.primary_contact_email,
            project_manager=pms.get(o.project_manager_id) if o.project_manager_id else None,
            projects=projects[o.id],
            contact_count=counts.get(o.id, 0),
        )
        for o in organisations
    ]


async def _check_project_manager(session: AsyncSession, user_id: uuid.UUID | None) -> None:
    if user_id is None:
        return
    found = await session.scalar(
        select(User.id).where(
            User.id == user_id,
            User.is_active.is_(True),
            pm_condition(),
        )
    )
    if found is None:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The project manager must be an active Project Manager.",
            [
                {
                    "field": "project_manager_id",
                    "issue": "not_project_manager",
                    "message": str(user_id),
                }
            ],
        )


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


async def insert_organisation(
    session: AsyncSession, actor: User, data: OrganisationCreate
) -> Organisation:
    """Add the organisation and its audit entry without committing (callers commit)."""
    if await _name_taken(session, data.name):
        raise _duplicate_name()
    await _check_project_manager(session, data.project_manager_id)
    organisation = Organisation(
        name=data.name,
        type=data.type.value,
        industry=data.industry,
        website=data.website,
        primary_contact_email=data.primary_contact_email,
        project_manager_id=data.project_manager_id,
    )
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
        after={"name": data.name, "type": data.type.value}
        | {field: _plain(getattr(data, field)) for field in DETAILS if getattr(data, field)},
    )
    if data.account_manager_ids:
        await _replace_account_managers(session, actor, organisation, data.account_manager_ids)
    return organisation


def _plain(value: object) -> object:
    return str(value) if isinstance(value, uuid.UUID) else value


async def update_organisation(
    session: AsyncSession, actor: User, organisation_id: uuid.UUID, data: OrganisationUpdate
) -> Organisation:
    organisation = await get_organisation(session, organisation_id)
    if data.version != organisation.version:
        raise _version_conflict()
    if organisation.archived_at is not None:
        raise AppError(409, "ORGANISATION_ARCHIVED", "The organisation is archived.")
    sent = data.model_fields_set
    if "name" in sent and data.name is None:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The request is not valid.",
            [{"field": "name", "issue": "required", "message": "Name is required."}],
        )
    changes: dict[str, object] = {}
    if data.name is not None and data.name != organisation.name:
        if await _name_taken(session, data.name, except_id=organisation.id):
            raise _duplicate_name()
        changes["name"] = data.name
    for field in DETAILS:
        if field in sent and getattr(data, field) != getattr(organisation, field):
            changes[field] = getattr(data, field)
    if "project_manager_id" in changes:
        await _check_project_manager(session, data.project_manager_id)
    managers_changed = False
    if data.account_manager_ids is not None:
        managers_changed = await _replace_account_managers(
            session, actor, organisation, data.account_manager_ids
        )
    if not changes and not managers_changed:
        return organisation
    if changes:
        before = {field: _plain(getattr(organisation, field)) for field in changes}
        for field, value in changes.items():
            setattr(organisation, field, value)
        record_audit(
            session,
            actor,
            "organisation.updated",
            "organisation",
            organisation.id,
            before=before,
            after={field: _plain(value) for field, value in changes.items()},
        )
    elif managers_changed:
        organisation.updated_at = datetime.now(UTC)  # bump the version: the form saved
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
    if await _replace_account_managers(session, actor, organisation, user_ids):
        try:
            await session.commit()
        except IntegrityError:  # someone else assigned the same person at the same moment
            await session.rollback()
            raise AppError(
                409, "CONFLICT", "The list was changed by someone else. Reload and try again."
            ) from None
    return (await account_managers(session, [organisation.id]))[organisation.id]


async def _replace_account_managers(
    session: AsyncSession, actor: User, organisation: Organisation, user_ids: list[uuid.UUID]
) -> bool:
    """Make the list exactly `user_ids` (not committed). True when something changed."""
    if organisation.type != OrganisationType.CLIENT.value:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Account managers can only be assigned to client organisations.",
        )
    await session.flush()  # a new organisation needs its row before the assignments
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
        return True
    return False


# --- named client contacts per project ----------------------------------------------------------


async def set_project_contacts(
    session: AsyncSession,
    actor: User,
    organisation_id: uuid.UUID,
    project_id: uuid.UUID,
    user_ids: list[uuid.UUID],
) -> OrganisationProject:
    """Replace the named client contacts of one of this client's projects. Only active client
    accounts of the organisation; at least one (the schema refuses an empty list)."""
    organisation = await get_organisation(session, organisation_id)
    if organisation.archived_at is not None:
        raise AppError(409, "ORGANISATION_ARCHIVED", "The organisation is archived.")
    project = await session.scalar(
        select(Project)
        .where(
            Project.id == project_id,
            Project.client_organisation_id == organisation.id,
            Project.archived_at.is_(None),
        )
        .with_for_update()
    )
    if project is None:
        raise AppError(404, "NOT_FOUND", "Project not found for this organisation.")
    wanted = set(user_ids)
    valid = set(
        await session.scalars(
            select(User.id).where(
                User.id.in_(wanted),
                User.is_active.is_(True),
                User.organisation_id == organisation.id,
                client_condition(),
            )
        )
    )
    invalid = wanted - valid
    if invalid:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Contacts must be active client accounts of this organisation.",
            [
                {"field": "user_ids", "issue": "not_a_client_contact", "message": str(user_id)}
                for user_id in sorted(invalid, key=str)
            ],
        )
    current = set(
        await session.scalars(
            select(ProjectClientContact.user_id).where(
                ProjectClientContact.project_id == project.id
            )
        )
    )
    if wanted != current:
        await session.execute(
            delete(ProjectClientContact).where(
                ProjectClientContact.project_id == project.id,
                ProjectClientContact.user_id.in_(current - wanted),
            )
        )
        session.add_all(
            ProjectClientContact(project_id=project.id, user_id=user_id, assigned_by=actor.id)
            for user_id in wanted - current
        )
        record_audit(
            session,
            actor,
            "project.client_contacts_changed",
            "project",
            project.id,
            project_id=project.id,
            before={"user_ids": sorted(str(i) for i in current)},
            after={"user_ids": sorted(str(i) for i in wanted)},
        )
        await session.commit()
    found = (await _projects(session, [organisation.id]))[organisation.id]
    return next(p for p in found if p.id == project.id)


async def projects_left_without_contact(session: AsyncSession, user: User) -> list[Project]:
    """Active projects where `user` is the last active named contact (removing them would
    leave the project without one)."""
    mine = select(ProjectClientContact.project_id).where(ProjectClientContact.user_id == user.id)
    others = (
        select(ProjectClientContact.project_id)
        .join(User, User.id == ProjectClientContact.user_id)
        .where(
            ProjectClientContact.user_id != user.id,
            User.is_active.is_(True),
            User.organisation_id == user.organisation_id,
        )
    )
    return list(
        await session.scalars(
            select(Project)
            .where(
                Project.id.in_(mine),
                Project.id.not_in(others),
                Project.archived_at.is_(None),
                Project.client_organisation_id == user.organisation_id,
            )
            .order_by(Project.code)
        )
    )
