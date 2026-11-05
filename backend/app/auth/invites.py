"""Invite links: a one-use link that lets a person set their own password.

The administrator creates the account (no password yet) and passes the link on. The person opens
it, chooses a password and the link is used up. The same link resets a forgotten password.
Only a hash of the token is stored; the token itself is shown once, in the API response.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.core.config import Settings
from app.core.errors import AppError
from app.users.models import User, UserInvite


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def invite_url(token: str, settings: Settings) -> str:
    """The address the administrator hands over. The token sits after `#`, so browsers never
    send it to a server or write it into an access log."""
    return f"{settings.invite_base_url}/set-password#token={token}"


async def issue_invite(
    session: AsyncSession, user: User, created_by: User, settings: Settings
) -> tuple[str, datetime]:
    """Make a new link for `user`; any older unused link stops working. Does not commit."""
    now = datetime.now(UTC)
    await session.execute(
        update(UserInvite)
        .where(
            UserInvite.user_id == user.id,
            UserInvite.used_at.is_(None),
            UserInvite.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(days=settings.invite_valid_days)
    session.add(
        UserInvite(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=expires_at,
            created_by=created_by.id,
        )
    )
    await session.flush()
    return token, expires_at


def invalid_invite() -> AppError:
    # One message for every failure (unknown, used, replaced, expired, account inactive).
    return AppError(
        400,
        "INVALID_INVITE",
        "This link is invalid or has expired. Ask your administrator for a new one.",
    )


async def accept_invite(session: AsyncSession, token: str, password: str) -> User:
    """Set the password of the person the link belongs to and use the link up. Commits."""
    invite = await session.scalar(
        select(UserInvite).where(UserInvite.token_hash == hash_token(token)).with_for_update()
    )
    now = datetime.now(UTC)
    if (
        invite is None
        or invite.used_at is not None
        or invite.revoked_at is not None
        or invite.expires_at <= now
    ):
        raise invalid_invite()
    user = await session.get(User, invite.user_id)
    if user is None or not user.is_active:
        raise invalid_invite()
    user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    invite.used_at = now
    await session.commit()
    return user


async def pending_invite_user_ids(
    session: AsyncSession, user_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of these users have a link that can still be used."""
    if not user_ids:
        return set()
    rows = await session.scalars(
        select(UserInvite.user_id).where(
            UserInvite.user_id.in_(user_ids),
            UserInvite.used_at.is_(None),
            UserInvite.revoked_at.is_(None),
            UserInvite.expires_at > datetime.now(UTC),
        )
    )
    return set(rows)
