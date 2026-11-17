"""API responses are never cached (propagation ticket): every client sees the latest data."""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from fastapi import FastAPI, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.main import create_app
from tests.conftest import make_project, make_user
from tests.test_auth import build_app, client_for
from tests.test_tasks import as_user


def _app() -> FastAPI:
    application = create_app()

    @application.get("/api/_test/own-cache")
    async def own_cache(response: Response) -> dict[str, str]:
        response.headers["Cache-Control"] = "private, max-age=60"
        return {}

    @application.get("/api/_test/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    return application


def _client(application: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


async def test_api_reads_writes_and_file_exports_are_not_stored(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, code="NOS")

    responses = [
        await client.get(f"/api/v1/projects/{project.id}/tasks", headers=as_user(pm)),
        await client.post(
            f"/api/v1/projects/{project.id}/tasks", headers=as_user(pm), json={"title": "New"}
        ),
        await client.get(f"/api/v1/projects/{project.id}/tasks/export", headers=as_user(pm)),
    ]

    assert [r.status_code for r in responses] == [200, 201, 200]
    assert all(r.headers["cache-control"] == "no-store" for r in responses)


async def test_errors_are_not_stored_either() -> None:
    async with _client(_app()) as http:
        missing = await http.get("/api/v1/nope")
        unauthenticated = await http.get("/api/v1/projects")
        crashed = await http.get("/api/_test/boom")

    assert missing.status_code == 404 and missing.headers["cache-control"] == "no-store"
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["cache-control"] == "no-store"
    assert crashed.status_code == 500 and crashed.headers["cache-control"] == "no-store"


async def test_a_route_with_its_own_cache_rule_keeps_it_and_health_is_untouched() -> None:
    async with _client(_app()) as http:
        own = await http.get("/api/_test/own-cache")
        health = await http.get("/health")

    assert own.headers["cache-control"] == "private, max-age=60"
    assert "cache-control" not in health.headers
