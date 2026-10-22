"""GET /users: the assignee picker (PM only), search and filters."""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.users.models import User
from tests.conftest import make_user
from tests.test_auth import HEADER, build_app, client_for

URL = "/api/v1/users"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


async def named(session: AsyncSession, name: str, email: str, role: GlobalRole) -> User:
    user = await make_user(session, role, email=email)
    user.name = name
    await session.flush()
    return user


async def test_pm_lists_active_users_sorted_by_name(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await named(session, "Zed PM", "zed@test.example", GlobalRole.PM)
    await named(session, "Bea Dev", "bea@test.example", GlobalRole.DEVELOPER)
    await named(session, "Al Dev", "al@test.example", GlobalRole.DEVELOPER)
    gone = await named(session, "Cy Gone", "cy@test.example", GlobalRole.DEVELOPER)
    gone.is_active = False
    await session.flush()

    response = await client.get(URL, headers={HEADER: str(pm.id)})

    assert response.status_code == 200
    body = response.json()
    assert [u["name"] for u in body["items"]] == ["Al Dev", "Bea Dev", "Zed PM"]
    assert body["total"] == 3 and body["page"] == 1
    assert set(body["items"][0]) == {"id", "name", "email", "role"}


async def test_search_by_name_or_email_and_role_filter(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await named(session, "Pat PM", "pat@test.example", GlobalRole.PM)
    await named(session, "Maria Lopez", "mlopez@test.example", GlobalRole.DEVELOPER)
    await named(session, "Marco Rossi", "rossi@test.example", GlobalRole.DEVELOPER)
    await named(session, "100% Dev", "pct@test.example", GlobalRole.DEVELOPER)
    headers = {HEADER: str(pm.id)}

    async def names(**params: str) -> list[str]:
        response = await client.get(URL, headers=headers, params=params)
        assert response.status_code == 200
        return [u["name"] for u in response.json()["items"]]

    assert await names(q="mar") == ["Marco Rossi", "Maria Lopez"]  # case-insensitive, by name
    assert await names(q="ROSSI@") == ["Marco Rossi"]  # matches the email too
    assert await names(q="%") == ["100% Dev"]  # % is a literal, not a wildcard
    assert await names(role="pm") == ["Pat PM"]
    assert await names(q="nobody") == []


async def test_pagination(client: httpx.AsyncClient, session: AsyncSession) -> None:
    pm = await named(session, "Pat PM", "pat@test.example", GlobalRole.PM)
    for i in range(3):
        await named(session, f"Dev {i}", f"d{i}@test.example", GlobalRole.DEVELOPER)

    response = await client.get(
        URL, headers={HEADER: str(pm.id)}, params={"page": 2, "page_size": 2}
    )

    body = response.json()
    assert body["total"] == 4 and body["page"] == 2 and len(body["items"]) == 2


async def test_developers_and_anonymous_are_refused(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    dev = await make_user(session)

    assert (await client.get(URL, headers={HEADER: str(dev.id)})).status_code == 403
    assert (await client.get(URL)).status_code == 401
