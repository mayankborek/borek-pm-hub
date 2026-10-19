"""Phase 1 identity: the caller names a seeded user in the X-Dev-User-Id header.

Only used when AUTH_MODE=dev (the app refuses to start with it in production).
"""

import uuid

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.users.models import User

DEV_USER_HEADER = "X-Dev-User-Id"


def unauthenticated(message: str) -> AppError:
    return AppError(401, "UNAUTHENTICATED", message)


async def authenticate(request: Request, session: AsyncSession) -> User:
    raw = request.headers.get(DEV_USER_HEADER)
    if not raw:
        raise unauthenticated(f"Missing {DEV_USER_HEADER} header.")
    try:
        user_id = uuid.UUID(raw)
    except ValueError:
        raise unauthenticated(f"{DEV_USER_HEADER} is not a valid user ID.") from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthenticated("Unknown or inactive user.")
    return user
