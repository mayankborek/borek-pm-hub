"""Email + password sign-in (AUTH_MODE=local): login, tokens, lockout, bootstrap accounts."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_access_token, hash_password, verify_password
from app.common.enums import GlobalRole
from app.core.config import Settings, get_settings
from app.users.models import User
from scripts.bootstrap_users import ensure_accounts
from tests.conftest import make_user
from tests.test_auth import HEADER, build_app, client_for

PASSWORD = "correct horse battery"
SETTINGS = Settings(auth_mode="local", environment="test", secret_key="k" * 40, max_failed_logins=3)


def local_app(session: AsyncSession) -> FastAPI:
    application = build_app(session)
    application.dependency_overrides[get_settings] = lambda: SETTINGS
    return application


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(local_app(session)) as http:
        yield http


async def account(session: AsyncSession, email: str = "pat@test.example") -> User:
    user = await make_user(session, GlobalRole.PM, email=email)
    user.password_hash = hash_password(PASSWORD)
    await session.flush()
    return user


async def login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_login_returns_a_token_that_opens_the_api(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    user = await account(session)

    response = await login(client, "  PAT@test.example ", PASSWORD)  # any case, trimmed

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 480 * 60
    assert body["user"] == {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": "pm",
    }
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200 and me.json()["id"] == str(user.id)


async def test_every_failure_looks_the_same(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await account(session)
    entra_only = await make_user(session, email="entra@test.example")  # no password hash
    gone = await account(session, "gone@test.example")
    gone.is_active = False
    await session.flush()

    responses = [
        await login(client, "pat@test.example", "wrong password"),
        await login(client, "nobody@test.example", PASSWORD),
        await login(client, entra_only.email, PASSWORD),
        await login(client, "gone@test.example", PASSWORD),
    ]

    assert {r.status_code for r in responses} == {401}
    assert len({r.json()["error"]["message"] for r in responses}) == 1
    assert responses[0].json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_lockout_after_repeated_failures_and_reset_on_success(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    user = await account(session)

    for _ in range(2):
        await login(client, user.email, "nope")
    ok = await login(client, user.email, PASSWORD)  # still allowed, resets the counter
    await session.refresh(user)
    assert ok.status_code == 200 and user.failed_login_count == 0

    for _ in range(3):
        await login(client, user.email, "nope")
    locked = await login(client, user.email, PASSWORD)  # right password, but locked
    assert locked.status_code == 401

    await session.refresh(user)
    assert user.locked_until is not None
    user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()
    assert (await login(client, user.email, PASSWORD)).status_code == 200


async def test_bad_tokens_and_dev_header_are_refused(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    user = await account(session)
    expired, _ = create_access_token(
        user.id, SETTINGS.model_copy(update={"access_token_minutes": -1})
    )
    other_key, _ = create_access_token(
        user.id, SETTINGS.model_copy(update={"secret_key": "z" * 40})
    )

    for headers in (
        {},
        {"Authorization": "Bearer garbage"},
        {"Authorization": f"Bearer {expired}"},
        {"Authorization": f"Bearer {other_key}"},
        {"Authorization": "Basic abc"},
        {HEADER: str(user.id)},  # the dev header means nothing in local mode
    ):
        response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401, headers


async def test_deactivated_user_loses_access_with_an_existing_token(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    user = await account(session)
    token, _ = create_access_token(user.id, SETTINGS)
    user.is_active = False
    await session.flush()

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 401


async def test_login_does_not_exist_outside_local_mode(session: AsyncSession) -> None:
    await account(session)
    async with client_for(build_app(session, auth_mode="dev")) as dev_client:
        response = await login(dev_client, "pat@test.example", PASSWORD)
    assert response.status_code == 404


def test_local_mode_needs_a_long_secret_key() -> None:
    with pytest.raises(ValidationError):
        Settings(auth_mode="local", secret_key="short")
    Settings(auth_mode="local", secret_key="k" * 32)  # fine


def test_password_hashing() -> None:
    hashed = hash_password("a long password")
    assert hashed != "a long password" and hashed.startswith("$argon2")
    assert verify_password("a long password", hashed)
    assert not verify_password("another one", hashed)
    assert not verify_password("anything", "not a hash")


async def test_bootstrap_creates_missing_accounts_once(session: AsyncSession) -> None:
    env = {"BOOTSTRAP_PM_PASSWORD": "pm-password-123", "BOOTSTRAP_DEV_PASSWORD": "short"}

    first = await ensure_accounts(session, env)
    second = await ensure_accounts(session, env)

    assert first[0].startswith("created qa.pm@borek.test") and first[1].startswith("skipped")
    assert second[0].startswith("kept")
    users = (await session.scalars(select(User))).all()
    assert [(u.email, u.global_role) for u in users] == [("qa.pm@borek.test", "pm")]
    assert users[0].password_hash and verify_password("pm-password-123", users[0].password_hash)

    new_env = {**env, "BOOTSTRAP_PM_PASSWORD": "new-password-456"}
    assert (await ensure_accounts(session, new_env))[0].startswith("kept")  # not overwritten
    reset = await ensure_accounts(session, new_env, reset_passwords=True)
    await session.refresh(users[0])
    assert reset[0].startswith("password set")
    assert verify_password("new-password-456", users[0].password_hash or "")
