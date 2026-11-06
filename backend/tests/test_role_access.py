"""Sprint 02-26: who reaches which project. Creator leads, Manager sees all, PM only own projects,
a plain member follows the developer rules, and a project always keeps a lead."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.projects.models import Project, ProjectMember
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for

URL = "/api/v1/projects"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def as_user(user: User) -> dict[str, str]:
    return {HEADER: str(user.id)}


async def join(session: AsyncSession, project: Project, user: User, role: str) -> None:
    session.add(ProjectMember(project_id=project.id, user_id=user.id, project_role=role))
    await session.flush()


class World:
    manager: User
    pm: User
    other_pm: User
    dev: User
    own: Project  # created and led by `pm`
    foreign: Project  # created and led by `other_pm`


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.manager = await make_user(session, GlobalRole.MANAGER)
    w.pm = await make_user(session, GlobalRole.PM)
    w.other_pm = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session)
    w.own = await make_project(session, w.pm.id, "OWN")
    w.foreign = await make_project(session, w.other_pm.id, "FOR")
    return w


async def role_of(session: AsyncSession, project_id: object, user: User) -> str | None:
    return await session.scalar(
        select(ProjectMember.project_role).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
        )
    )


# --- the creator leads --------------------------------------------------------------------------


@pytest.mark.parametrize("role", [GlobalRole.PM, GlobalRole.MANAGER])
async def test_creator_becomes_project_lead(
    client: httpx.AsyncClient, session: AsyncSession, role: GlobalRole
) -> None:
    creator = await make_user(session, role)
    response = await client.post(URL, headers=as_user(creator), json={"code": "NEW", "name": "New"})
    assert response.status_code == 201
    assert [m["project_role"] for m in response.json()["members"]] == ["project_lead"]


async def test_creator_listed_as_plain_member_is_one_lead_row(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    response = await client.post(
        URL,
        headers=as_user(pm),
        json={
            "code": "NEW",
            "name": "New",
            "members": [{"user_id": str(pm.id), "project_role": "developer"}],
        },
    )
    assert response.status_code == 201
    assert [(m["user_id"], m["project_role"]) for m in response.json()["members"]] == [
        (str(pm.id), "project_lead")
    ]


# --- archive ------------------------------------------------------------------------------------


async def test_archiving_records_who_did_it_and_twice_keeps_the_first(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    url = f"{URL}/{world.own.id}"
    assert (await client.delete(url, headers=as_user(world.pm))).status_code == 204
    assert (await client.delete(url, headers=as_user(world.manager))).status_code == 204
    await session.refresh(world.own)
    body = (await client.get(url, headers=as_user(world.manager))).json()
    assert body["archived_by"] == str(world.pm.id)


async def test_pm_keeps_read_access_to_an_archived_project_they_led(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await join(session, world.own, world.dev, "developer")
    world.own.archived_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(world.own)
    url = f"{URL}/{world.own.id}"

    assert (await client.get(url, headers=as_user(world.pm))).status_code == 200
    update = await client.patch(
        url, headers=as_user(world.pm), json={"version": world.own.version, "name": "Changed"}
    )
    assert update.status_code == 409  # read-only
    assert (await client.get(url, headers=as_user(world.dev))).status_code == 404  # as before
    assert (await client.get(url, headers=as_user(world.other_pm))).status_code == 404

    listed = await client.get(URL, headers=as_user(world.pm), params={"include_archived": True})
    assert "OWN" in [p["code"] for p in listed.json()["items"]]
    assert "OWN" not in [
        p["code"] for p in (await client.get(URL, headers=as_user(world.pm))).json()["items"]
    ]


async def test_pm_who_archived_a_project_sees_it_without_being_a_lead(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.foreign.archived_at = datetime.now(UTC)
    world.foreign.archived_by = world.pm.id
    await session.flush()
    await session.refresh(world.foreign)
    url = f"{URL}/{world.foreign.id}"
    assert (await client.get(url, headers=as_user(world.pm))).status_code == 200
    listed = await client.get(URL, headers=as_user(world.pm), params={"include_archived": True})
    assert "FOR" in [p["code"] for p in listed.json()["items"]]


async def test_plain_member_pm_does_not_see_an_archived_project(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await join(session, world.foreign, world.pm, "developer")
    world.foreign.archived_at = datetime.now(UTC)
    await session.flush()
    response = await client.get(f"{URL}/{world.foreign.id}", headers=as_user(world.pm))
    assert response.status_code == 404
    listed = await client.get(URL, headers=as_user(world.pm), params={"include_archived": True})
    assert "FOR" not in [p["code"] for p in listed.json()["items"]]


# --- PM only in own projects --------------------------------------------------------------------


async def foreign_requests(world: World) -> list[tuple[str, str, dict[str, object] | None]]:
    project = f"{URL}/{world.foreign.id}"
    return [
        ("GET", project, None),
        ("PATCH", project, {"version": 1, "name": "x"}),
        ("DELETE", project, None),
        ("GET", f"{project}/members", None),
        ("POST", f"{project}/members", {"user_id": str(world.dev.id)}),
        ("DELETE", f"{project}/members/{world.other_pm.id}", None),
        ("GET", f"{project}/statuses", None),
        ("POST", f"{project}/statuses", {"name": "New", "category": "todo"}),
        ("GET", f"{project}/tasks", None),
        ("POST", f"{project}/tasks", {"title": "x"}),
        ("GET", f"{project}/tasks/export", None),
    ]


async def test_pm_gets_404_everywhere_in_a_foreign_project(
    client: httpx.AsyncClient, world: World
) -> None:
    for method, url, body in await foreign_requests(world):
        response = await client.request(method, url, headers=as_user(world.pm), json=body)
        assert response.status_code == 404, (method, url, response.text)


async def test_pm_gets_404_on_tasks_of_a_foreign_project(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.foreign, world.other_pm.id)
    url = f"/api/v1/tasks/{task.id}"
    for method, path, body in (
        ("GET", url, None),
        ("PATCH", url, {"version": 1, "title": "x"}),
        ("DELETE", url, None),
        ("PUT", f"{url}/assignee", {"version": 1, "assignee_id": None}),
        ("GET", f"{url}/comments", None),
        ("POST", f"{url}/comments", {"body": "x"}),
        ("GET", f"{url}/activity", None),
        ("GET", f"{url}/attachments", None),
    ):
        response = await client.request(method, path, headers=as_user(world.pm), json=body)
        assert response.status_code == 404, (method, path, response.text)


async def test_pm_who_is_a_plain_member_has_developer_rights(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await join(session, world.foreign, world.pm, "developer")
    task = await make_task(session, world.foreign, world.other_pm.id)
    mine = await make_task(session, world.foreign, world.other_pm.id, assignee_id=world.pm.id)
    await session.refresh(world.foreign)
    headers = as_user(world.pm)
    project = f"{URL}/{world.foreign.id}"

    assert (await client.get(project, headers=headers)).status_code == 200
    assert (await client.get(f"{project}/tasks", headers=headers)).status_code == 200
    for method, url, body in (
        ("PATCH", project, {"version": 1, "name": "x"}),
        ("POST", f"{project}/members", {"user_id": str(world.dev.id)}),
        ("PATCH", f"/api/v1/tasks/{task.id}", {"version": 1, "title": "x"}),
        ("PUT", f"/api/v1/tasks/{task.id}/assignee", {"version": 1, "assignee_id": None}),
        ("DELETE", f"/api/v1/tasks/{task.id}", None),
    ):
        response = await client.request(method, url, headers=headers, json=body)
        assert response.status_code == 403, (method, url, response.text)
    priority = await client.patch(
        f"/api/v1/tasks/{mine.id}", headers=headers, json={"version": 1, "priority": "high"}
    )
    assert priority.status_code == 200  # the developer rule: on a task assigned to them


async def test_pm_leads_their_own_project_fully(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    headers = as_user(world.pm)
    project = f"{URL}/{world.own.id}"
    task = await make_task(session, world.own, world.pm.id)
    await session.refresh(world.own)
    body = {"version": world.own.version, "name": "Mine"}
    assert (await client.patch(project, headers=headers, json=body)).status_code == 200
    assert (
        await client.post(
            f"{project}/members", headers=headers, json={"user_id": str(world.dev.id)}
        )
    ).status_code == 201
    assert (
        await client.patch(
            f"/api/v1/tasks/{task.id}", headers=headers, json={"version": 1, "title": "Renamed"}
        )
    ).status_code == 200


async def test_only_a_lead_sees_archived_tasks_of_a_project(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await join(session, world.own, world.dev, "developer")
    task = await make_task(session, world.own, world.pm.id, archived_at=datetime.now(UTC))
    url = f"/api/v1/tasks/{task.id}"
    tasks = f"{URL}/{world.own.id}/tasks"
    params = {"include_archived": True}

    assert (await client.get(url, headers=as_user(world.pm))).status_code == 200
    assert (await client.get(url, headers=as_user(world.dev))).status_code == 404
    lead_list = await client.get(tasks, headers=as_user(world.pm), params=params)
    member_list = await client.get(tasks, headers=as_user(world.dev), params=params)
    assert lead_list.json()["total"] == 1
    assert member_list.json()["total"] == 0


async def test_pm_who_is_a_plain_member_does_not_get_archived_tasks(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    """A PM may ask for archived tasks in general, but only gets them where they lead."""
    await join(session, world.foreign, world.pm, "developer")
    await make_task(session, world.foreign, world.other_pm.id, archived_at=datetime.now(UTC))
    await session.refresh(world.foreign)
    tasks = f"{URL}/{world.foreign.id}/tasks"
    params = {"include_archived": True}

    listed = await client.get(tasks, headers=as_user(world.pm), params=params)
    assert listed.json()["total"] == 0
    exported = await client.get(f"{tasks}/export", headers=as_user(world.pm), params=params)
    assert len(exported.text.strip().splitlines()) == 1  # the header row only
    lead = await client.get(tasks, headers=as_user(world.other_pm), params=params)
    assert lead.json()["total"] == 1


# --- lists and dashboards never show foreign projects -------------------------------------------


async def test_lists_and_dashboards_are_limited_to_own_projects(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    today = date.today()
    await make_task(session, world.own, world.pm.id, title="Mine", due_date=today - timedelta(1))
    await make_task(
        session, world.foreign, world.other_pm.id, title="Theirs", due_date=today - timedelta(1)
    )
    await make_task(session, world.foreign, world.other_pm.id, title="Theirs too", status="Blocked")
    headers = as_user(world.pm)

    projects = (await client.get(URL, headers=headers)).json()
    assert [p["code"] for p in projects["items"]] == ["OWN"]
    assert projects["total"] == 1

    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()
    assert [t["title"] for t in tasks["items"]] == ["Mine"]

    export = await client.get("/api/v1/tasks/export", headers=headers)
    assert "Mine" in export.text and "Theirs" not in export.text

    board = (await client.get("/api/v1/dashboard", headers=headers)).json()
    assert [p["code"] for p in board["projects"]] == ["OWN"]
    assert board["projects_total"] == 1
    assert board["summary"]["total"] == 1
    assert [t["title"] for t in board["overdue"]["items"]] == ["Mine"]
    assert board["blocked"]["items"] == []


async def test_a_plain_member_pm_sees_that_project_in_lists(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await join(session, world.foreign, world.pm, "developer")
    projects = (await client.get(URL, headers=as_user(world.pm))).json()
    assert [p["code"] for p in projects["items"]] == ["FOR", "OWN"]


async def test_cross_project_lists_do_not_give_a_pm_archived_tasks(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.own, world.pm.id, archived_at=datetime.now(UTC))
    response = await client.get(
        "/api/v1/tasks", headers=as_user(world.pm), params={"include_archived": True}
    )
    assert response.json()["total"] == 0


async def test_the_picker_still_lists_people_from_outside_the_pms_projects(
    client: httpx.AsyncClient, world: World
) -> None:
    """The picker is how a PM adds new people, so it cannot be limited to current members."""
    listed = (await client.get("/api/v1/users", headers=as_user(world.pm))).json()
    assert {str(world.dev.id), str(world.manager.id)} <= {u["id"] for u in listed["items"]}


# --- Manager ------------------------------------------------------------------------------------


async def test_manager_sees_and_runs_every_project_without_being_a_member(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    headers = as_user(world.manager)
    project = f"{URL}/{world.foreign.id}"
    task = await make_task(session, world.foreign, world.other_pm.id)
    await session.refresh(world.foreign)

    codes = [p["code"] for p in (await client.get(URL, headers=headers)).json()["items"]]
    assert codes == ["FOR", "OWN"]
    board = (await client.get("/api/v1/dashboard", headers=headers)).json()
    assert [p["code"] for p in board["projects"]] == ["FOR", "OWN"]
    assert (await client.get("/api/v1/tasks", headers=headers)).json()["total"] == 1
    body = {"version": world.foreign.version, "name": "Renamed"}
    assert (await client.patch(project, headers=headers, json=body)).status_code == 200
    await session.refresh(world.foreign)
    assert (
        await client.patch(
            f"/api/v1/tasks/{task.id}", headers=headers, json={"version": 1, "title": "Renamed"}
        )
    ).status_code == 200
    archived = await client.get(URL, headers=headers, params={"include_archived": True})
    assert archived.status_code == 200


async def test_manager_has_no_access_to_user_administration(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await client.get("/api/v1/admin/users", headers=as_user(world.manager))
    assert response.status_code == 403


# --- members ------------------------------------------------------------------------------------


async def test_manager_manages_members_in_any_project(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    base, headers = f"{URL}/{world.foreign.id}/members", as_user(world.manager)
    added = await client.post(
        base, headers=headers, json={"user_id": str(world.dev.id), "project_role": "project_lead"}
    )
    assert added.status_code == 201
    changed = await client.patch(
        f"{base}/{world.other_pm.id}", headers=headers, json={"project_role": "developer"}
    )
    assert changed.status_code == 200
    removed = await client.delete(f"{base}/{world.other_pm.id}", headers=headers)
    assert removed.status_code == 204
    assert await role_of(session, world.foreign.id, world.other_pm) is None


async def test_last_lead_cannot_be_removed_or_demoted(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    base, headers = f"{URL}/{world.own.id}/members/{world.pm.id}", as_user(world.manager)

    removed = await client.delete(base, headers=headers)
    assert removed.status_code == 409
    assert removed.json()["error"]["code"] == "LAST_PROJECT_LEAD"
    demoted = await client.patch(base, headers=headers, json={"project_role": "developer"})
    assert demoted.status_code == 409
    assert demoted.json()["error"]["code"] == "LAST_PROJECT_LEAD"
    assert await role_of(session, world.own.id, world.pm) == "project_lead"


async def test_one_of_two_leads_can_go_and_a_plain_member_is_never_blocked(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await join(session, world.own, world.other_pm, "project_lead")
    await join(session, world.own, world.dev, "developer")
    base, headers = f"{URL}/{world.own.id}/members", as_user(world.pm)
    assert (await client.delete(f"{base}/{world.dev.id}", headers=headers)).status_code == 204
    assert (await client.delete(f"{base}/{world.other_pm.id}", headers=headers)).status_code == 204
    blocked = await client.delete(f"{base}/{world.pm.id}", headers=headers)
    assert blocked.status_code == 409


@pytest.mark.parametrize("role", [GlobalRole.ADMIN, GlobalRole.ACCOUNT_MANAGER, GlobalRole.CLIENT])
async def test_people_outside_project_work_cannot_be_members(
    client: httpx.AsyncClient, session: AsyncSession, world: World, role: GlobalRole
) -> None:
    person = await make_user(session, role)
    response = await client.post(
        f"{URL}/{world.own.id}/members", headers=as_user(world.pm), json={"user_id": str(person.id)}
    )
    assert response.status_code == 422
