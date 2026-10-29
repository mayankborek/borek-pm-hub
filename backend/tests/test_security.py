"""Security hardening: headers, body size, docs in production, login rate limit, sign-out,
token claims, client IP behind proxies, upload content types, PII-free DB error logs."""

import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.auth import rate_limit
from app.auth.rate_limit import SlidingWindowLimiter, client_ip
from app.auth.security import create_access_token
from app.common.enums import GlobalRole
from app.core.config import get_settings
from app.core.errors import _db_error_summary
from app.main import create_app
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for
from tests.test_login import PASSWORD, SETTINGS, account, local_app, login

API = "/api/v1"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- headers and docs ---------------------------------------------------------------------------


async def test_security_headers_on_success_and_error(session: AsyncSession) -> None:
    async with client_for(build_app(session)) as client:
        for response in (await client.get("/health"), await client.get(f"{API}/auth/me")):
            headers = response.headers
            assert headers["x-content-type-options"] == "nosniff"
            assert headers["x-frame-options"] == "DENY"
            assert headers["referrer-policy"] == "no-referrer"
            assert (
                headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
            )
            assert headers["cache-control"] == "no-store"
            assert "strict-transport-security" not in headers  # local/test: no HSTS
        docs = await client.get("/docs")
        assert docs.status_code == 200 and "content-security-policy" not in docs.headers


@pytest.fixture
def production_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("SECRET_KEY", "p" * 40)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.usefixtures("production_env")
async def test_api_docs_are_off_in_production_and_hsts_is_on() -> None:
    async with client_for(create_app()) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await client.get(path)).status_code == 404, path
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.headers["strict-transport-security"] == "max-age=31536000"


async def test_cors_allows_only_the_headers_the_frontend_sends(session: AsyncSession) -> None:
    async with client_for(build_app(session)) as client:
        preflight = await client.options(
            f"{API}/projects",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        evil = await client.options(
            f"{API}/projects",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in evil.headers


# --- request body size --------------------------------------------------------------------------


async def test_oversized_bodies_are_refused_before_sign_in(session: AsyncSession) -> None:
    big = b"x" * (1024 * 1024 + 1)

    async def chunks() -> AsyncIterator[bytes]:  # no Content-Length: counted while read
        for _ in range(3):
            yield b"y" * (512 * 1024)

    async with client_for(build_app(session)) as client:
        declared = await client.post(
            f"{API}/projects", content=big, headers={"Content-Type": "application/json"}
        )
        streamed = await client.post(
            f"{API}/projects", content=chunks(), headers={"Content-Type": "application/json"}
        )
        small = await client.post(f"{API}/projects", json={"code": "X"})

    for response in (declared, streamed):
        assert response.status_code == 413, response.text
        assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
        assert response.headers["x-request-id"]
    assert small.status_code == 401  # normal bodies still reach the sign-in check


# --- login rate limit ---------------------------------------------------------------------------


async def test_login_is_rate_limited_per_client(session: AsyncSession) -> None:
    await account(session)
    application = local_app(session)
    limited = SETTINGS.model_copy(update={"login_rate_limit_per_minute": 3})
    application.dependency_overrides[get_settings] = lambda: limited

    async with client_for(application) as client:
        answers = [await login(client, "pat@test.example", "wrong") for _ in range(3)]
        blocked = await login(client, "pat@test.example", PASSWORD)

    assert {r.status_code for r in answers} == {401}
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert int(blocked.headers["retry-after"]) >= 1


def test_sliding_window_frees_slots_after_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])
    limiter = SlidingWindowLimiter(window_seconds=60)

    assert limiter.hit("a", 2) is None and limiter.hit("a", 2) is None
    assert limiter.hit("a", 2) == 61
    assert limiter.hit("b", 2) is None  # other clients are not affected
    assert limiter.hit("a", 0) is None  # 0 = no limit
    now[0] += 61
    assert limiter.hit("a", 2) is None


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "client": (peer, 1234), "headers": headers})


def test_client_ip_behind_our_proxies_can_not_be_forged() -> None:
    # without trust (dev, tests): always the direct peer
    assert client_ip(_request("172.18.0.5", "9.9.9.9"), False) == "172.18.0.5"
    # behind nginx (+ host proxy): the right-most address that is not one of our proxies
    assert client_ip(_request("172.18.0.5", "9.9.9.9, 172.17.0.1"), True) == "9.9.9.9"
    # a forged left part is ignored
    assert client_ip(_request("172.18.0.5", "1.2.3.4, 9.9.9.9"), True) == "9.9.9.9"
    # a public peer is a direct visitor: its header is not trusted
    assert client_ip(_request("8.8.4.4", "1.2.3.4"), True) == "8.8.4.4"
    assert client_ip(_request("172.18.0.5"), True) == "172.18.0.5"


# --- sessions and tokens ------------------------------------------------------------------------


async def test_logout_ends_every_session_of_the_user(session: AsyncSession) -> None:
    user = await account(session)
    other = await account(session, "other@test.example")
    async with client_for(local_app(session)) as client:
        laptop = (await login(client, user.email, PASSWORD)).json()["access_token"]
        phone = (await login(client, user.email, PASSWORD)).json()["access_token"]
        colleague = (await login(client, other.email, PASSWORD)).json()["access_token"]
        # several sessions at once are allowed
        for token in (laptop, phone):
            assert (await client.get(f"{API}/auth/me", headers=bearer(token))).status_code == 200

        assert (await client.post(f"{API}/auth/logout", headers=bearer(laptop))).status_code == 204

        for token in (laptop, phone):
            ended = await client.get(f"{API}/auth/me", headers=bearer(token))
            assert ended.status_code == 401
        assert (await client.get(f"{API}/auth/me", headers=bearer(colleague))).status_code == 200
        fresh = (await login(client, user.email, PASSWORD)).json()["access_token"]
        assert (await client.get(f"{API}/auth/me", headers=bearer(fresh))).status_code == 200
        assert (await client.post(f"{API}/auth/logout")).status_code == 401


async def test_tokens_need_issuer_audience_and_version(session: AsyncSession) -> None:
    user = await account(session)
    staging, _ = create_access_token(
        user.id, SETTINGS.model_copy(update={"environment": "staging"})
    )
    no_version = jwt.encode(
        {"sub": str(user.id), "iss": "borek-pm-hub", "aud": "test", "exp": 9999999999},
        SETTINGS.secret_key,
        algorithm="HS256",
    )
    wrong_issuer = jwt.encode(
        {"sub": str(user.id), "ver": 0, "iss": "x", "aud": "test", "exp": 9999999999},
        SETTINGS.secret_key,
        algorithm="HS256",
    )
    good, _ = create_access_token(user.id, SETTINGS)
    async with client_for(local_app(session)) as client:
        for token in (staging, no_version, wrong_issuer):
            assert (await client.get(f"{API}/auth/me", headers=bearer(token))).status_code == 401
        assert (await client.get(f"{API}/auth/me", headers=bearer(good))).status_code == 200


# --- uploads ------------------------------------------------------------------------------------


async def test_download_type_comes_from_the_extension(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        pm = await make_user(session, GlobalRole.PM)
        project = await make_project(session, pm.id)
        task = await make_task(session, project, pm.id)
        async with client_for(build_app(session)) as client:
            uploaded = await client.post(
                f"{API}/tasks/{task.id}/attachments",
                headers={HEADER: str(pm.id)},
                files={"file": ("pic.png", b"<script>alert(1)</script>", "text/html")},
            )
            assert uploaded.status_code == 201, uploaded.text
            assert uploaded.json()["content_type"] == "image/png"
            download = await client.get(
                uploaded.json()["download_url"], headers={HEADER: str(pm.id)}
            )
        assert download.headers["content-type"] == "image/png"
        assert download.headers["content-disposition"].startswith("attachment")
    finally:
        get_settings.cache_clear()


# --- logs ---------------------------------------------------------------------------------------


def test_database_error_logs_carry_no_row_values() -> None:
    cause = SimpleNamespace(sqlstate="23505", constraint_name="uq_users_email")
    orig = SimpleNamespace(__cause__=cause)
    exc = SimpleNamespace(orig=orig)
    summary = _db_error_summary(exc)  # type: ignore[arg-type]
    assert summary == "SimpleNamespace sqlstate=23505 constraint=uq_users_email"
    assert "@" not in summary


# --- security event log -------------------------------------------------------------------------


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


async def test_sign_in_events_are_logged_without_secrets(session: AsyncSession) -> None:
    user = await account(session)
    application = local_app(session)  # create_app() resets the root handlers: attach after it
    collected = _Collect()
    security_log = logging.getLogger("app.security")
    security_log.addHandler(collected)
    try:
        async with client_for(application) as client:
            await login(client, "nobody@test.example", "guess-1")
            for _ in range(SETTINGS.max_failed_logins):
                await login(client, user.email, "guess-2")
            await client.get(f"{API}/auth/me", headers=bearer("garbage"))
    finally:
        security_log.removeHandler(collected)

    text = "\n".join(collected.lines)
    assert "event=login_failed" in text and "reason=unknown_email" in text
    assert "reason=wrong_password" in text and f"user_id={user.id}" in text
    assert "event=account_locked" in text and "event=unauthenticated" in text
    for secret in ("guess-1", "guess-2", "nobody@test.example", user.email, "garbage"):
        assert secret not in text
