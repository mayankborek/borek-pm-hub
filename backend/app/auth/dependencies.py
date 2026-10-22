"""get_current_user(): the one place that turns a request into a User."""

from typing import Annotated

from fastapi import Depends, Request

from app.auth.providers import dev, entra, local
from app.core.config import Settings, get_settings
from app.core.database import SessionDep
from app.users.models import User


async def get_current_user(
    request: Request, session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> User:
    if settings.auth_mode == "local":
        return await local.authenticate(request, session, settings)
    provider = entra if settings.auth_mode == "entra" else dev
    return await provider.authenticate(request, session)


CurrentUser = Annotated[User, Depends(get_current_user)]
