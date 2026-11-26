"""Account Manager role guide (26.11.2026): project status, membership without lead, My Work."""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.organisations.models import Organisation, OrganisationAccountManager
from app.projects.models import Project
from app.users.models import User
from tests.conftest import make_project, make_user
from tests.test_auth import HEADER, build_app, client_for

PROJECTS = "/api/v1/projects"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def as_user(user: User) -> dict[str, str]:
    return {HEADER: str(user.id)}


class World:
    pm: User
    dev: User
    am: User
    served: Project  # external, client assigned to `am`
    unserved: Project  # external, another client
    internal: Project  # no client; `am` is not a member at the start


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.pm = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session)
    w.am = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    mine = Organisation(name="Acme", type="client")
    other = Organisation(name="Globex", type="client")
    session.add_all([mine, other])
    await session.flush()
    session.add(OrganisationAccountManager(organisation_id=mine.id, user_id=w.am.id))
    w.served = await make_project(session, w.pm.id, "SRV")
    w.unserved = await make_project(session, w.pm.id, "UNS")
    w.internal = await make_project(session, w.pm.id, "INT")
    w.served.client_organisation_id = mine.id
    w.unserved.client_organisation_id = other.id
    w.served.project_type = w.unserved.project_type = "external"
    await session.flush()
    for project in (w.served, w.unserved, w.internal):
        await session.refresh(project)
    return w


async def test_account_manager_changes_only_the_status_of_their_clients_projects(
    client: httpx.AsyncClient, world: World
) -> None:
    headers = as_user(world.am)
    url = f"{PROJECTS}/{world.served.id}"
    changed = await client.patch(
        url, headers=headers, json={"version": world.served.version, "status": "on_hold"}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["status"] == "on_hold"
    version = changed.json()["version"]

    # status together with any other field is a normal project edit
    both = await client.patch(
        url, headers=headers, json={"version": version, "status": "active", "name": "x"}
    )
    assert both.status_code == 403
    # another client's project or an internal one: not even visible
    for project in (world.unserved, world.internal):
        response = await client.patch(
            f"{PROJECTS}/{project.id}",
            headers=headers,
            json={"version": project.version, "status": "on_hold"},
        )
        assert response.status_code == 404


async def test_developer_member_cannot_change_project_status(
    client: httpx.AsyncClient, world: World
) -> None:
    url = f"{PROJECTS}/{world.internal.id}"
    added = await client.post(
        f"{url}/members", headers=as_user(world.pm), json={"user_id": str(world.dev.id)}
    )
    assert added.status_code == 201
    response = await client.patch(
        url,
        headers=as_user(world.dev),
        json={"version": world.internal.version, "status": "on_hold"},
    )
    assert response.status_code == 403


async def test_account_manager_joins_a_project_works_on_own_tasks_and_sees_them_in_my_work(
    client: httpx.AsyncClient, world: World
) -> None:
    url = f"{PROJECTS}/{world.internal.id}"
    assert (await client.get(url, headers=as_user(world.am))).status_code == 404

    picker = await client.get("/api/v1/users", headers=as_user(world.pm))
    assert str(world.am.id) in [u["id"] for u in picker.json()["items"]]
    added = await client.post(
        f"{url}/members", headers=as_user(world.pm), json={"user_id": str(world.am.id)}
    )
    assert added.status_code == 201, added.text

    headers = as_user(world.am)
    codes = {p["code"] for p in (await client.get(PROJECTS, headers=headers)).json()["items"]}
    assert codes == {"SRV", "INT"}
    created = await client.post(f"{url}/tasks", headers=headers, json={"title": "Prepare demo"})
    assert created.status_code == 201, created.text
    assert created.json()["assignee"]["id"] == str(world.am.id)

    mine = (await client.get("/api/v1/me/tasks", headers=headers)).json()["items"]
    assert [t["title"] for t in mine] == ["Prepare demo"]
    work = await client.get("/api/v1/dashboard/me", headers=headers)
    assert work.status_code == 200
    assert work.json()["summary"]["total"] == 1

    # a member, not a lead: no project edits, no member management, and no status change on a
    # project that is not their client's
    for method, path, body in (
        ("PATCH", url, {"version": world.internal.version, "status": "on_hold"}),
        ("PATCH", url, {"version": world.internal.version, "name": "x"}),
        ("POST", f"{url}/members", {"user_id": str(world.dev.id)}),
    ):
        response = await client.request(method, path, headers=headers, json=body)
        assert response.status_code == 403, (method, path, response.text)


async def test_portfolio_and_oversight_stay_on_their_clients_projects(
    client: httpx.AsyncClient, world: World
) -> None:
    """Membership opens the project, not the money in the portfolio."""
    added = await client.post(
        f"{PROJECTS}/{world.internal.id}/members",
        headers=as_user(world.pm),
        json={"user_id": str(world.am.id)},
    )
    assert added.status_code == 201
    headers = as_user(world.am)
    portfolio = (await client.get("/api/v1/portfolio", headers=headers)).json()
    assert [p["code"] for p in portfolio["items"]] == ["SRV"]
    money = await client.get(f"{PROJECTS}/{world.internal.id}/finance", headers=headers)
    assert money.status_code == 403


async def test_account_manager_is_never_project_lead(
    client: httpx.AsyncClient, world: World
) -> None:
    url = f"{PROJECTS}/{world.internal.id}/members"
    lead = await client.post(
        url,
        headers=as_user(world.pm),
        json={"user_id": str(world.am.id), "project_role": "project_lead"},
    )
    assert lead.status_code == 422
    assert lead.json()["error"]["details"][0]["issue"] == "account_manager_cannot_lead"

    added = await client.post(url, headers=as_user(world.pm), json={"user_id": str(world.am.id)})
    assert added.status_code == 201
    promote = await client.patch(
        f"{url}/{world.am.id}", headers=as_user(world.pm), json={"project_role": "project_lead"}
    )
    assert promote.status_code == 422
    assert promote.json()["error"]["details"][0]["issue"] == "account_manager_cannot_lead"
