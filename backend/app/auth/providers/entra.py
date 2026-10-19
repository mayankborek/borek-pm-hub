"""Microsoft Entra ID provider (later).

Planned: validate the bearer token (issuer, audience, signature via Microsoft's public keys),
then map the Entra object ID in the token to `users.external_id` and read the app role.
Routers, services and `can()` do not change when this replaces the dev provider.
"""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.users.models import User


async def authenticate(request: Request, session: AsyncSession) -> User:
    raise AppError(501, "NOT_IMPLEMENTED", "Entra ID sign-in is not available yet.")
