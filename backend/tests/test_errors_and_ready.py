"""Error shape, request IDs and the readiness probe."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import AppError
from app.main import create_app


class Item(BaseModel):
    name: str


def _app() -> FastAPI:
    application = create_app()

    @application.get("/_test/app-error")
    async def app_error() -> None:
        raise AppError(
            409, "TASK_VERSION_CONFLICT", "Changed by someone else.", [{"field": "version"}]
        )

    @application.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @application.post("/_test/items")
    async def items(item: Item) -> Item:
        return item

    return application


def _client(application: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_app_error_uses_the_standard_shape() -> None:
    async with _client(_app()) as client:
        response = await client.get("/_test/app-error")
    body = response.json()
    assert response.status_code == 409
    assert body["error"] == {
        "code": "TASK_VERSION_CONFLICT",
        "message": "Changed by someone else.",
        "details": [{"field": "version"}],
    }
    assert body["request_id"] == response.headers["X-Request-ID"]


async def test_unknown_route_uses_the_standard_shape() -> None:
    async with _client(_app()) as client:
        response = await client.get("/api/v1/nope")
    body = response.json()
    assert response.status_code == 404
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"] == []


async def test_validation_error_lists_the_fields() -> None:
    async with _client(_app()) as client:
        response = await client.post("/_test/items", json={})
    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"][0]["field"] == "name"


async def test_unexpected_error_hides_internals_but_keeps_request_id() -> None:
    async with _client(_app()) as client:
        response = await client.get("/_test/boom", headers={"X-Request-ID": "abc-123"})
    assert response.status_code == 500
    assert "secret" not in response.text
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["request_id"] == "abc-123"


async def test_request_id_is_generated_when_missing_or_unsafe() -> None:
    async with _client(_app()) as client:
        generated = await client.get("/health")
        too_long = await client.get("/health", headers={"X-Request-ID": "x" * 200})
    assert len(generated.headers["X-Request-ID"]) == 32
    assert too_long.headers["X-Request-ID"] != "x" * 200


async def test_ready_reports_ok_with_a_working_database(session: AsyncSession) -> None:
    application = _app()

    async def override() -> AsyncIterator[AsyncSession]:
        yield session

    application.dependency_overrides[get_session] = override
    async with _client(application) as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


async def test_ready_returns_503_when_the_database_is_down() -> None:
    class BrokenSession:
        async def execute(self, *args: Any, **kwargs: Any) -> None:
            raise ConnectionRefusedError("db down at 10.0.0.5")

    application = _app()

    async def override() -> AsyncIterator[Any]:
        yield BrokenSession()

    application.dependency_overrides[get_session] = override
    async with _client(application) as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert "10.0.0.5" not in response.text
