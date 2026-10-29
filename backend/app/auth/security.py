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


_ISSUER = "borek-pm-hub"


def create_access_token(
    user_id: uuid.UUID, settings: Settings, token_version: int = 0
) -> tuple[str, int]:
    """Return (token, seconds until it expires).

    `aud` is the environment, so a token from staging never opens production even if the
    secret key were reused. `ver` is the user's token_version; signing out raises it, which
    ends every token issued before.
    """
    expires_in = settings.access_token_minutes * 60
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "ver": token_version,
        "iss": _ISSUER,
        "aud": settings.environment,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=_ALGORITHM), expires_in


def read_access_token(token: str, settings: Settings) -> tuple[uuid.UUID, int] | None:
    """(user id, token version) of a valid, unexpired token, or None."""
    try:
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            audience=settings.environment,
            options={"require": ["sub", "exp", "iss", "aud", "ver"]},
        )
        version = claims["ver"]
        if not isinstance(version, int) or isinstance(version, bool):
            return None
        return uuid.UUID(claims["sub"]), version
    except (jwt.PyJWTError, ValueError, TypeError):
        return None
