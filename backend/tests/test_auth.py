"""Dev sign-in, /auth/dev-users and /auth/me, plus 401/403/404 through a real request."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, Resource, require
from app.common.enums import GlobalRole
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.main import create_app
from app.projects.membership import is_member
from app.projects.models import ProjectMember
from tests.conftest import make_project, make_user

HEADER = "X-Dev-User-Id"


def build_app(session: AsyncSession, auth_mode: str = "dev") -> FastAPI:
    application = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode=auth_mode, environment="test"
    )

    @application.post("/_test/projects")
    async def create_project(user: CurrentUser) -> dict[str, str]:
        require(user, Action.PROJECT_CREATE)
        return {"ok": "yes"}

    @application.get("/_test/projects/{project_id}")
    async def view_project(project_id: uuid.UUID, user: CurrentUser) -> dict[str, str]:
        member = await is_member(session, user.id, project_id)
        require(user, Action.PROJECT_VIEW, Resource(project_id=project_id, is_member=member))
        return {"ok": "yes"}

    return application


def client_for(application: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


async def test_dev_users_lists_active_users_without_signing_in(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM, "pm@t.example")
    dev = await make_user(session, GlobalRole.DEVELOPER, "dev@t.example")
    inactive = await make_user(session, GlobalRole.DEVELOPER, "gone@t.example")
    inactive.is_active = False
    await session.flush()

    response = await client.get("/api/v1/auth/dev-users")

    assert response.status_code == 200
    by_id = {u["id"]: u for u in response.json()}
    assert set(by_id) == {str(pm.id), str(dev.id)}
    assert by_id[str(pm.id)]["role"] == "pm"
    assert set(by_id[str(pm.id)]) == {"id", "name", "email", "role"}


async def test_dev_users_is_hidden_when_not_in_dev_mode(session: AsyncSession) -> None:
    async with client_for(build_app(session, auth_mode="entra")) as http:
        response = await http.get("/api/v1/auth/dev-users")
    assert response.status_code == 404


async def test_me_returns_profile_role_and_memberships(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session, GlobalRole.DEVELOPER, "dev@t.example")
    alpha = await make_project(session, pm.id, "ALPHA")
    await make_project(session, pm.id, "OTHER")  # dev is not a member of this one
    session.add(ProjectMember(project_id=alpha.id, user_id=dev.id, project_role="project_lead"))
    await session.flush()

    response = await client.get("/api/v1/auth/me", headers={HEADER: str(dev.id)})

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(dev.id)
    assert body["role"] == "developer"
    assert body["email"] == "dev@t.example"
    assert body["is_active"] is True
    assert body["memberships"] == [
        {
            "project_id": str(alpha.id),
            "project_code": "ALPHA",
            "project_name": "Test project",
            "project_role": "project_lead",
        }
    ]


async def test_me_leaves_out_archived_projects(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    from datetime import UTC, datetime

    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session, GlobalRole.DEVELOPER)
    project = await make_project(session, pm.id, "OLD")
    project.archived_at = datetime.now(UTC)
    session.add(ProjectMember(project_id=project.id, user_id=dev.id))
    await session.flush()

    response = await client.get("/api/v1/auth/me", headers={HEADER: str(dev.id)})

    assert response.json()["memberships"] == []


async def test_missing_header_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_garbage_unknown_and_inactive_users_are_401(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    inactive = await make_user(session)
    inactive.is_active = False
    await session.flush()
    for value in ("not-a-uuid", str(uuid.uuid4()), str(inactive.id)):
        response = await client.get("/api/v1/auth/me", headers={HEADER: value})
        assert response.status_code == 401, value


async def test_entra_mode_does_not_accept_the_dev_header(session: AsyncSession) -> None:
    user = await make_user(session, GlobalRole.PM)
    async with client_for(build_app(session, auth_mode="entra")) as http:
        response = await http.get("/api/v1/auth/me", headers={HEADER: str(user.id)})
    assert response.status_code == 501


async def test_developer_is_forbidden_from_pm_only_endpoint_pm_is_allowed(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session, GlobalRole.DEVELOPER)

    as_dev = await client.post("/_test/projects", headers={HEADER: str(dev.id)})
    as_pm = await client.post("/_test/projects", headers={HEADER: str(pm.id)})
    anonymous = await client.post("/_test/projects")

    assert as_dev.status_code == 403
    assert as_dev.json()["error"]["code"] == "FORBIDDEN"
    assert as_pm.status_code == 200
    assert anonymous.status_code == 401


async def test_non_member_gets_404_member_gets_200(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    member = await make_user(session, GlobalRole.DEVELOPER)
    outsider = await make_user(session, GlobalRole.DEVELOPER)
    project = await make_project(session, pm.id)
    session.add(ProjectMember(project_id=project.id, user_id=member.id))
    await session.flush()
    url = f"/_test/projects/{project.id}"

    assert (await client.get(url, headers={HEADER: str(member.id)})).status_code == 200
    assert (await client.get(url, headers={HEADER: str(outsider.id)})).status_code == 404
    assert (await client.get(url, headers={HEADER: str(pm.id)})).status_code == 200
