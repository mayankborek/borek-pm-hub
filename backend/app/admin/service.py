"""User administration: create, list, edit, deactivate, invite links (admin only).

Rules enforced here (the router only checks that the caller is an administrator):
- an email is unique, whatever the letter case;
- an administrator cannot demote or deactivate themselves;
- at least one active administrator always remains.
"""

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Literal

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import AdminProjectOut, AdminUserCreate, AdminUserOut, AdminUserUpdate
from app.auth.invites import issue_invite, pending_invite_user_ids
from app.auth.permissions import admin_condition, is_admin
from app.common.enums import GlobalRole
from app.common.validation import like_escape
from app.core.config import Settings
from app.core.errors import AppError
from app.projects.models import Project, ProjectMember
from app.users.models import User

StatusFilter = Literal["active", "inactive", "all"]


def _not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "User not found.")


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise _not_found()
    return user


async def _email_taken(session: AsyncSession, email: str, *, except_id: uuid.UUID | None) -> bool:
    query = select(User.id).where(func.lower(User.email) == email)
    if except_id is not None:
        query = query.where(User.id != except_id)
    return await session.scalar(query) is not None


def _email_conflict() -> AppError:
    return AppError(409, "EMAIL_TAKEN", "A user with this email already exists.")


async def _ensure_another_admin(session: AsyncSession, target: User) -> None:
    """Fail unless an active administrator other than `target` exists.

    All active administrators are locked first, so two administrators removing each other at
    the same moment are handled one after the other and the second one is refused.
    """
    ids = await session.scalars(
        select(User.id)
        .where(admin_condition(), User.is_active.is_(True))
        .order_by(User.id)
        .with_for_update()
    )
    if not any(found != target.id for found in ids):
        raise AppError(409, "LAST_ADMIN", "At least one active administrator must remain.")


# --- reading ------------------------------------------------------------------------------------


async def to_out(session: AsyncSession, users: list[User]) -> list[AdminUserOut]:
    """Add each person's active projects and whether an invite link is still open."""
    ids = [u.id for u in users]
    projects: dict[uuid.UUID, list[AdminProjectOut]] = defaultdict(list)
    if ids:
        rows = await session.execute(
            select(ProjectMember.user_id, Project.id, Project.code, Project.name)
            .join(Project, Project.id == ProjectMember.project_id)
            .where(ProjectMember.user_id.in_(ids), Project.archived_at.is_(None))
            .order_by(Project.code)
        )
        for user_id, project_id, code, name in rows:
            projects[user_id].append(AdminProjectOut(id=project_id, code=code, name=name))
    pending = await pending_invite_user_ids(session, ids)
    return [
        AdminUserOut(
            id=u.id,
            name=u.name,
            email=u.email,
            role=u.global_role,
            is_active=u.is_active,
            join_date=u.join_date,
            password_set=u.password_hash is not None,
            invite_pending=u.id in pending,
            projects=projects[u.id],
            created_at=u.created_at,
        )
        for u in users
    ]


async def list_users(
    session: AsyncSession,
    *,
    q: str | None,
    role: GlobalRole | None,
    status: StatusFilter,
    page: int,
    page_size: int,
) -> tuple[list[User], int, int]:
    """Returns (users on this page, total matching, how many of those are active)."""
    conditions: list[ColumnElement[bool]] = []
    if role is not None:
        conditions.append(User.global_role == role.value)
    if status == "active":
        conditions.append(User.is_active.is_(True))
    elif status == "inactive":
        conditions.append(User.is_active.is_(False))
    if q and q.strip():
        pattern = f"%{like_escape(q.strip())}%"
        conditions.append(
            or_(User.name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\"))
        )
    total = await session.scalar(select(func.count(User.id)).where(*conditions)) or 0
    active_total = (
        await session.scalar(
            select(func.count(User.id)).where(*conditions, User.is_active.is_(True))
        )
        or 0
    )
    rows = await session.scalars(
        select(User)
        .where(*conditions)
        .order_by(User.name, User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total, active_total


# --- writing ------------------------------------------------------------------------------------


async def create_user(
    session: AsyncSession, actor: User, data: AdminUserCreate, settings: Settings
) -> tuple[User, str, datetime]:
    """Create an account without a password and its first invite link. Commits."""
    if await _email_taken(session, data.email, except_id=None):
        raise _email_conflict()
    user = User(
        name=data.name, email=data.email, global_role=data.role.value, join_date=data.join_date
    )
    session.add(user)
    await session.flush()
    token, expires_at = await issue_invite(session, user, actor, settings)
    await session.commit()
    return user, token, expires_at


async def update_user(
    session: AsyncSession, actor: User, user_id: uuid.UUID, data: AdminUserUpdate
) -> User:
    user = await get_user(session, user_id)
    changes = data.model_dump(exclude_unset=True)
    if "role" in changes and changes["role"].value != user.global_role:
        if user.id == actor.id:
            raise AppError(409, "CANNOT_CHANGE_OWN_ROLE", "You cannot change your own role.")
        if is_admin(user) and user.is_active:
            await _ensure_another_admin(session, user)
        user.global_role = changes["role"].value
    if "email" in changes and changes["email"] != user.email:
        if await _email_taken(session, changes["email"], except_id=user.id):
            raise _email_conflict()
        user.email = changes["email"]
    if "name" in changes:
        user.name = changes["name"]
    if "join_date" in changes:
        user.join_date = changes["join_date"]
    await session.commit()
    return user


async def set_active(
    session: AsyncSession, actor: User, user_id: uuid.UUID, *, active: bool
) -> User:
    """Deactivating blocks sign-in at once, even with a token that is still valid. Tasks stay
    assigned to the person. Commits."""
    user = await get_user(session, user_id)
    if not active and user.is_active:
        if user.id == actor.id:
            raise AppError(409, "CANNOT_DEACTIVATE_SELF", "You cannot deactivate your own account.")
        if is_admin(user):
            await _ensure_another_admin(session, user)
    user.is_active = active
    await session.commit()
    return user


async def new_invite(
    session: AsyncSession, actor: User, user_id: uuid.UUID, settings: Settings
) -> tuple[User, str, datetime]:
    """A fresh link (also to reset a forgotten password); older unused links stop working."""
    user = await get_user(session, user_id)
    if not user.is_active:
        raise AppError(409, "USER_INACTIVE", "Activate the user before creating a link.")
    token, expires_at = await issue_invite(session, user, actor, settings)
    await session.commit()
    return user, token, expires_at
