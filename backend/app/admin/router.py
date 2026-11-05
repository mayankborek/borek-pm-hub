"""Administration of user accounts (administrator only)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.admin.schemas import (
    AdminUserCreate,
    AdminUserCreatedOut,
    AdminUserListOut,
    AdminUserOut,
    AdminUserUpdate,
    InviteOut,
)
from app.auth.dependencies import CurrentUser
from app.auth.invites import invite_url
from app.auth.permissions import Action, require
from app.common.enums import GlobalRole
from app.common.validation import PageParam, PageSizeParam
from app.core.config import Settings, get_settings
from app.core.database import SessionDep
from app.users.models import User

router = APIRouter(prefix="/admin/users", tags=["admin"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def _one(session: AsyncSession, user: User) -> AdminUserOut:
    return (await service.to_out(session, [user]))[0]


def _no_store(response: Response) -> None:
    """The response holds a link that works once: keep it out of caches."""
    response.headers["Cache-Control"] = "no-store"


async def _with_invite(
    session: AsyncSession,
    response: Response,
    settings: Settings,
    user: User,
    token: str,
    expires_at: datetime,
) -> AdminUserCreatedOut:
    _no_store(response)
    return AdminUserCreatedOut(
        user=await _one(session, user),
        invite=InviteOut(url=invite_url(token, settings), expires_at=expires_at),
    )


@router.get("", response_model=AdminUserListOut)
async def list_users(
    actor: CurrentUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100, description="Search name or email")] = None,
    role: Annotated[GlobalRole | None, Query(description="Filter by role")] = None,
    status: Annotated[
        service.StatusFilter, Query(description="active, inactive or all (default)")
    ] = "all",
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> AdminUserListOut:
    require(actor, Action.ADMIN_USERS)
    users, total, active_total = await service.list_users(
        session, q=q, role=role, status=status, page=page, page_size=page_size
    )
    return AdminUserListOut(
        items=await service.to_out(session, users),
        total=total,
        active_total=active_total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=AdminUserCreatedOut, status_code=201)
async def create_user(
    body: AdminUserCreate,
    actor: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> AdminUserCreatedOut:
    """Creates the account without a password and returns its invite link (shown only once)."""
    require(actor, Action.ADMIN_USERS)
    user, token, expires_at = await service.create_user(session, actor, body, settings)
    response.headers["Location"] = f"/api/v1/admin/users/{user.id}"
    return await _with_invite(session, response, settings, user, token, expires_at)


@router.get("/{user_id}", response_model=AdminUserOut)
async def get_user(user_id: uuid.UUID, actor: CurrentUser, session: SessionDep) -> AdminUserOut:
    require(actor, Action.ADMIN_USERS)
    return await _one(session, await service.get_user(session, user_id))


@router.patch("/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: uuid.UUID, body: AdminUserUpdate, actor: CurrentUser, session: SessionDep
) -> AdminUserOut:
    require(actor, Action.ADMIN_USERS)
    return await _one(session, await service.update_user(session, actor, user_id, body))


@router.post("/{user_id}/deactivate", response_model=AdminUserOut)
async def deactivate_user(
    user_id: uuid.UUID, actor: CurrentUser, session: SessionDep
) -> AdminUserOut:
    require(actor, Action.ADMIN_USERS)
    return await _one(session, await service.set_active(session, actor, user_id, active=False))


@router.post("/{user_id}/activate", response_model=AdminUserOut)
async def activate_user(
    user_id: uuid.UUID, actor: CurrentUser, session: SessionDep
) -> AdminUserOut:
    require(actor, Action.ADMIN_USERS)
    return await _one(session, await service.set_active(session, actor, user_id, active=True))


@router.post("/{user_id}/invite", response_model=AdminUserCreatedOut)
async def create_invite(
    user_id: uuid.UUID,
    actor: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> AdminUserCreatedOut:
    """A new link, for a person who lost theirs or forgot their password. The older link stops
    working. The link is shown only once."""
    require(actor, Action.ADMIN_USERS)
    user, token, expires_at = await service.new_invite(session, actor, user_id, settings)
    return await _with_invite(session, response, settings, user, token, expires_at)
