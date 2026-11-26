"""get_current_user(): the one place that turns a request into a User."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select

from app.access_policy.models import RolePermissionSetting
from app.auth.policy import attach_role_policy
from app.auth.providers import dev, entra, local
from app.core.config import Settings, get_settings
from app.core.database import SessionDep
from app.users.models import User


async def get_current_user(
    request: Request, session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> User:
    if settings.auth_mode == "local":
        user = await local.authenticate(request, session, settings)
    else:
        provider = entra if settings.auth_mode == "entra" else dev
        user = await provider.authenticate(request, session)
    # The administrator's role matrix switches for this role, read fresh on every request.
    rows = await session.execute(
        select(RolePermissionSetting.permission, RolePermissionSetting.enabled).where(
            RolePermissionSetting.role == user.global_role
        )
    )
    attach_role_policy(user, {permission: enabled for permission, enabled in rows.all()})
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
