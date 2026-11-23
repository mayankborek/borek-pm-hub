"""In-app notifications: writing (`notify`), reading, settings and cleanup.

`notify` adds rows to the caller's session, so a notification is saved, or undone, together with
the change that caused it. Who receives what is decided in `app.notifications.events`, with the
same visibility rules as the API. Reading re-checks access: notifications about projects the
person can no longer see are not returned (a removed member, an archived project).
"""

import base64
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import (
    client_condition,
    is_admin,
    is_client,
    manager_condition,
    sees_all_projects,
)
from app.common.enums import ProjectRole, ProjectType
from app.core.errors import AppError
from app.notifications.models import Notification, NotificationSetting
from app.notifications.schemas import (
    NotificationActor,
    NotificationOut,
    NotificationProject,
    SettingOut,
)
from app.organisations.models import OrganisationAccountManager
from app.projects.membership import visible_project_ids
from app.projects.models import Project, ProjectMember
from app.users.models import User

RETENTION_DAYS = 90
MAX_PAGE = 50

# Settings people can switch off. Tasks follow Jira: you hear about a task because of your
# relation to it (assignee, creator, mentioned). Clients only get the project-level ones.
STAFF_SETTINGS = (
    "tasks_assigned",  # tasks assigned to me: assigned, unassigned, changed, comments, files
    "tasks_reported",  # tasks I created: changed, comments, files
    "mentions",  # someone @mentioned me in a comment
    "blocked_tasks",  # project leads: a task in my project was blocked
    "change_requests",
    "requirements",
    "reports",
    "milestones",  # project leads and Managers: milestones moved, reached, running late
)
CLIENT_SETTINGS = ("change_requests", "requirements", "reports", "milestones")


def settings_for(user: User) -> tuple[str, ...]:
    if is_admin(user):
        return ()
    return CLIENT_SETTINGS if is_client(user) else STAFF_SETTINGS


# A recipient and the setting the notification falls under for them. When someone appears more
# than once, the first entry wins, so callers list the strongest reason first.
Recipient = tuple[uuid.UUID, str]


# --- writing ------------------------------------------------------------------------------------


async def notify(
    session: AsyncSession,
    actor: User | None,
    type_: str,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    project_id: uuid.UUID | None,
    params: dict[str, Any],
    recipients: Sequence[Recipient],
) -> int:
    """Add one notification per recipient, except the actor, inactive people and people who
    switched the setting off. The caller commits. Returns how many were added."""
    wanted: dict[uuid.UUID, str] = {}
    for user_id, setting in recipients:
        if actor is None or user_id != actor.id:
            wanted.setdefault(user_id, setting)
    if not wanted:
        return 0
    rows = await session.execute(
        select(User, NotificationSetting.muted)
        .outerjoin(NotificationSetting, NotificationSetting.user_id == User.id)
        .where(User.id.in_(list(wanted)), User.is_active.is_(True))
    )
    added = 0
    for user, muted in rows.all():
        setting = wanted[user.id]
        if setting not in settings_for(user) or setting in (muted or []):
            continue
        session.add(
            Notification(
                recipient_id=user.id,
                type=type_,
                setting=setting,
                project_id=project_id,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_id=actor.id if actor else None,
                params=params,
            )
        )
        added += 1
    return added


# --- recipients ---------------------------------------------------------------------------------


async def project_leads(session: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        await session.scalars(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == project_id,
                ProjectMember.project_role == ProjectRole.PROJECT_LEAD.value,
            )
        )
    )


async def managers(session: AsyncSession) -> list[uuid.UUID]:
    """Every active Manager (they oversee all projects)."""
    return list(
        await session.scalars(select(User.id).where(manager_condition(), User.is_active.is_(True)))
    )


async def account_managers(session: AsyncSession, project: Project) -> list[uuid.UUID]:
    """The Account Managers of the project's client."""
    if project.client_organisation_id is None:
        return []
    return list(
        await session.scalars(
            select(OrganisationAccountManager.user_id).where(
                OrganisationAccountManager.organisation_id == project.client_organisation_id
            )
        )
    )


async def client_contacts(session: AsyncSession, project: Project) -> list[uuid.UUID]:
    """Client contacts who see this project in the portal (same rule as the portal)."""
    if (
        project.project_type != ProjectType.EXTERNAL.value
        or project.client_organisation_id is None
        or project.archived_at is not None
    ):
        return []
    return list(
        await session.scalars(
            select(User.id).where(
                User.organisation_id == project.client_organisation_id,
                client_condition(),
                User.is_active.is_(True),
            )
        )
    )


# --- reading ------------------------------------------------------------------------------------


def _visible(user: User) -> ColumnElement[bool]:
    """Notifications the user may still see: those without a project, and those of projects the
    user reaches today."""
    no_project = Notification.project_id.is_(None)
    if is_admin(user):
        return no_project
    if is_client(user):
        if user.organisation_id is None:
            return no_project
        projects = select(Project.id).where(
            Project.client_organisation_id == user.organisation_id,
            Project.project_type == ProjectType.EXTERNAL.value,
            Project.archived_at.is_(None),
        )
    elif sees_all_projects(user):
        projects = select(Project.id).where(Project.archived_at.is_(None))
    else:
        projects = visible_project_ids(user)
    return or_(no_project, Notification.project_id.in_(projects))


def _mine(user: User) -> list[ColumnElement[bool]]:
    return [Notification.recipient_id == user.id, _visible(user)]


def _encode(n: Notification) -> str:
    raw = f"{n.created_at.isoformat()}|{n.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        at, ident = raw.split("|")
        return datetime.fromisoformat(at), uuid.UUID(ident)
    except (ValueError, UnicodeDecodeError):
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The request is not valid.",
            [{"field": "cursor", "issue": "invalid", "message": "Use next_cursor as it came."}],
        ) from None


async def unread_count(session: AsyncSession, user: User) -> int:
    return (
        await session.scalar(
            select(func.count(Notification.id)).where(*_mine(user), Notification.read_at.is_(None))
        )
        or 0
    )


async def list_notifications(
    session: AsyncSession, user: User, *, unread_only: bool, cursor: str | None, limit: int
) -> tuple[list[NotificationOut], str | None]:
    conditions = _mine(user)
    if unread_only:
        conditions.append(Notification.read_at.is_(None))
    if cursor:
        at, ident = _decode(cursor)
        conditions.append(
            or_(
                Notification.created_at < at,
                and_(Notification.created_at == at, Notification.id < ident),
            )
        )
    rows = list(
        await session.scalars(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit + 1)
        )
    )
    more = len(rows) > limit
    rows = rows[:limit]
    project_ids = {n.project_id for n in rows if n.project_id}
    projects = (
        {p.id: p for p in await session.scalars(select(Project).where(Project.id.in_(project_ids)))}
        if project_ids
        else {}
    )
    actor_ids = {n.actor_id for n in rows if n.actor_id}
    actors = (
        {u.id: u for u in await session.scalars(select(User).where(User.id.in_(actor_ids)))}
        if actor_ids
        else {}
    )
    out = []
    for n in rows:
        p = projects.get(n.project_id) if n.project_id else None
        a = actors.get(n.actor_id) if n.actor_id else None
        out.append(
            NotificationOut(
                id=n.id,
                type=n.type,
                setting=n.setting,
                project=NotificationProject(id=p.id, code=p.code, name=p.name) if p else None,
                entity_type=n.entity_type,
                entity_id=n.entity_id,
                actor=NotificationActor(id=a.id, name=a.name) if a else None,
                params=n.params,
                created_at=n.created_at,
                read_at=n.read_at,
            )
        )
    return out, _encode(rows[-1]) if more and rows else None


async def mark_read(session: AsyncSession, user: User, notification_id: uuid.UUID) -> None:
    """Idempotent. 404 for someone else's notification or one the user can no longer see."""
    found = await session.scalar(
        select(Notification).where(Notification.id == notification_id, *_mine(user))
    )
    if found is None:
        raise AppError(404, "NOT_FOUND", "Notification not found.")
    if found.read_at is None:
        found.read_at = datetime.now(UTC)
        await session.commit()


async def mark_all_read(session: AsyncSession, user: User) -> int:
    result = await session.execute(
        update(Notification)
        .where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
        .values(read_at=func.now())
    )
    await session.commit()
    return int(result.rowcount or 0)


# --- settings -----------------------------------------------------------------------------------


async def get_settings(session: AsyncSession, user: User) -> list[SettingOut]:
    row = await session.get(NotificationSetting, user.id)
    muted = set(row.muted) if row else set()
    return [SettingOut(key=key, enabled=key not in muted) for key in settings_for(user)]


async def update_settings(
    session: AsyncSession, user: User, changes: dict[str, bool]
) -> list[SettingOut]:
    allowed = settings_for(user)
    unknown = sorted(set(changes) - set(allowed))
    if unknown:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The request is not valid.",
            [
                {
                    "field": "settings",
                    "issue": "unknown_setting",
                    "message": "Not a setting for your role: " + ", ".join(unknown),
                }
            ],
        )
    row = await session.get(NotificationSetting, user.id)
    if row is None:
        row = NotificationSetting(user_id=user.id, muted=[])
        session.add(row)
    muted = set(row.muted)
    for key, enabled in changes.items():
        if enabled:
            muted.discard(key)
        else:
            muted.add(key)
    row.muted = [key for key in allowed if key in muted]  # stable order
    await session.commit()
    return await get_settings(session, user)


# --- retention ----------------------------------------------------------------------------------


async def delete_old(session: AsyncSession, *, days: int = RETENTION_DAYS) -> int:
    """Delete notifications older than `days` (read or not). Returns how many were deleted."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await session.execute(delete(Notification).where(Notification.created_at < cutoff))
    await session.commit()
    return int(result.rowcount or 0)
