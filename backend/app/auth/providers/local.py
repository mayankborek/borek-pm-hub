"""Email + password identity (AUTH_MODE=local): the caller sends `Authorization: Bearer <token>`.

Tokens come from POST /auth/login. Accounts are created by hand (SQL or scripts); see the README.
"""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.providers.dev import unauthenticated
from app.auth.security import read_access_token
from app.core.config import Settings
from app.users.models import User


async def authenticate(request: Request, session: AsyncSession, settings: Settings) -> User:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthenticated("Missing bearer token.")
    user_id = read_access_token(token.strip(), settings)
    if user_id is None:
        raise unauthenticated("Invalid or expired token.")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthenticated("Unknown or inactive user.")
    return user
