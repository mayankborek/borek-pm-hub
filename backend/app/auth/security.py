"""Password hashing (Argon2) and access tokens (signed JWT) for AUTH_MODE=local."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings

_hasher = PasswordHasher()
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# Verified when the email is unknown, so "no such user" takes as long as "wrong password".
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def create_access_token(user_id: uuid.UUID, settings: Settings) -> tuple[str, int]:
    """Return (token, seconds until it expires)."""
    expires_in = settings.access_token_minutes * 60
    now = datetime.now(UTC)
    claims = {"sub": str(user_id), "iat": now, "exp": now + timedelta(seconds=expires_in)}
    return jwt.encode(claims, settings.secret_key, algorithm=_ALGORITHM), expires_in


def read_access_token(token: str, settings: Settings) -> uuid.UUID | None:
    """The user id in a valid, unexpired token, or None."""
    try:
        claims = jwt.decode(
            token, settings.secret_key, algorithms=[_ALGORITHM], options={"require": ["sub", "exp"]}
        )
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
