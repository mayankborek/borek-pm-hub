import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.auth.dependencies import CurrentUser
from app.auth.events import email_hash, security_event
from app.auth.rate_limit import SlidingWindowLimiter, client_ip
from app.auth.schemas import LoginIn, LoginOut, MembershipOut, MeOut, UserOut
from app.auth.security import burn_password_check, create_access_token, verify_password
from app.core.config import Settings, get_settings
from app.core.database import SessionDep
from app.core.errors import AppError
from app.projects.membership import list_memberships
from app.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_user_out(user: User) -> UserOut:
    return UserOut(id=user.id, name=user.name, email=user.email, role=user.global_role)


@router.get("/dev-users", response_model=list[UserOut])
async def dev_users(
    session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> list[UserOut]:
    """Phase 1 user picker. Not available once real sign-in (AUTH_MODE=entra) is on."""
    if settings.auth_mode != "dev":
        raise AppError(404, "NOT_FOUND", "Not found.")
    result = await session.scalars(
        select(User).where(User.is_active.is_(True)).order_by(User.global_role, User.name)
    )
    return [_to_user_out(user) for user in result]


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser, session: SessionDep) -> MeOut:
    memberships = await list_memberships(session, user.id)
    return MeOut(
        **_to_user_out(user).model_dump(),
        is_active=user.is_active,
        memberships=[
            MembershipOut(
                project_id=m.project_id,
                project_code=m.project_code,
                project_name=m.project_name,
                project_role=m.project_role,
            )
            for m in memberships
        ],
    )


def _invalid_credentials() -> AppError:
    # One message for every failure (unknown email, wrong password, inactive, locked).
    return AppError(401, "INVALID_CREDENTIALS", "Invalid email or password.")


def _check_rate_limit(request: Request, settings: Settings) -> None:
    limiter: SlidingWindowLimiter = request.app.state.login_limiter
    client = client_ip(request, settings.trust_proxy_headers)
    retry_after = limiter.hit(client, settings.login_rate_limit_per_minute)
    if retry_after is not None:
        security_event("login_rate_limited", request, retry_after=retry_after)
        raise AppError(
            429,
            "RATE_LIMITED",
            "Too many sign-in attempts. Please wait a minute and try again.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("/login", response_model=LoginOut)
async def login(
    body: LoginIn,
    request: Request,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginOut:
    """Email + password sign-in. Only available when AUTH_MODE=local."""
    if settings.auth_mode != "local":
        raise AppError(404, "NOT_FOUND", "Not found.")
    _check_rate_limit(request, settings)
    # Row lock: parallel wrong guesses must not overwrite each other's failure count.
    user = await session.scalar(
        select(User).where(func.lower(User.email) == body.email.strip().lower()).with_for_update()
    )
    now = datetime.now(UTC)
    if (
        user is None
        or not user.is_active
        or user.password_hash is None
        or (user.locked_until is not None and user.locked_until > now)
    ):
        burn_password_check(body.password)
        if user is None:
            security_event(
                "login_failed", request, reason="unknown_email", email_hash=email_hash(body.email)
            )
        else:
            reason = (
                "locked" if user.is_active and user.password_hash else "inactive_or_no_password"
            )
            security_event("login_failed", request, user_id=user.id, reason=reason)
        raise _invalid_credentials()
    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_login_count = 0
            security_event(
                "account_locked", request, user_id=user.id, minutes=settings.lockout_minutes
            )
        else:
            security_event(
                "login_failed",
                request,
                user_id=user.id,
                reason="wrong_password",
                failures=user.failed_login_count,
            )
        await session.commit()
        raise _invalid_credentials()
    user.failed_login_count = 0
    user.locked_until = None
    await session.commit()
    token, expires_in = create_access_token(user.id, settings, user.token_version)
    security_event("login_succeeded", request, level=logging.INFO, user_id=user.id)
    return LoginOut(access_token=token, expires_in=expires_in, user=_to_user_out(user))


@router.post("/logout", status_code=204)
async def logout(user: CurrentUser, request: Request, session: SessionDep) -> None:
    """Sign out everywhere: every token issued to this user so far stops working.

    A user can be signed in on several devices or tabs at once (one token each); this ends
    all of them. The client also deletes its own copy of the token.
    """
    user.token_version += 1
    await session.commit()
    security_event("logout_all_sessions", request, level=logging.INFO, user_id=user.id)
