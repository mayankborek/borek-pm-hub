"""PM design spec (19.11.2026) backend updates: project Overview task stats, several people in
the task filter, and an editable reporter."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.projects.models import Project, ProjectMember
from app.users.models import User
from tests.conftest import make_project, make_task, make_user, status_by_name
from tests.test_auth import HEADER, build_app, client_for

API = "/api/v1"
TODAY = datetime.now(UTC).date()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


async def call(
    client: httpx.AsyncClient,
    user: User,
    method: str,
    path: str,
    body: Any = None,
    params: Any = None,
) -> httpx.Response:
    return await client.request(
        method, API + path, headers={HEADER: str(user.id)}, json=body, params=params
    )


async def ok(client: httpx.AsyncClient, user: User, method: str, path: str, **kw: Any) -> Any:
    response = await call(client, user, method, path, **kw)
    assert response.status_code < 300, response.text
    return response.json() if response.content else None


class World:
    pm: User
    dev: User
    other_dev: User
    outsider: User
    project: Project


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.pm = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session)
    w.other_dev = await make_user(session)
    w.outsider = await make_user(session)
    w.pm.name, w.dev.name, w.other_dev.name = "Alex Morgan", "Mia Chen", "Noah Park"
    w.project = await make_project(session, w.pm.id, code="PMD")  # the PM leads it
    for person in (w.dev, w.other_dev):
        session.add(ProjectMember(project_id=w.project.id, user_id=person.id))
    await session.flush()
    return w


# --- project Overview task stats --------------------------------------------------------------


def stats_path(w: World) -> str:
    return f"/projects/{w.project.id}/task-stats"


async def test_an_empty_project_has_zero_counts_and_no_progress(
    client: httpx.AsyncClient, world: World
) -> None:
    stats = await ok(client, world.pm, "GET", stats_path(world))

    assert (stats["total"], stats["open"], stats["completed"]) == (0, 0, 0)
    assert stats["progress_percent"] is None  # no division by zero
    assert stats["team_members"] == 3
    assert stats["next_milestone"] is None
    assert [c["status"]["name"] for c in stats["by_status"]] == [
        "Backlog",
        "To do",
        "In progress",
        "Code review",
        "Testing",
        "Blocked",
        "Done",
    ]
    assert all(c["count"] == 0 for c in stats["by_status"])
    assert [p["priority"] for p in stats["by_priority"]] == [
        "highest",
        "high",
        "medium",
        "low",
        "lowest",
    ]


async def test_stats_count_tasks_per_status_priority_and_due_window(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    sunday = TODAY + timedelta(days=6 - TODAY.weekday())
    p, s = world.project, session
    await make_task(s, p, world.pm.id, status="To do", priority="high", due_date=TODAY)
    await make_task(s, p, world.pm.id, status="To do", priority="medium", due_date=sunday)
    await make_task(
        s, p, world.pm.id, status="In progress", priority="medium", due_date=sunday + timedelta(1)
    )
    await make_task(
        s, p, world.pm.id, status="Blocked", priority="highest", due_date=TODAY - timedelta(1)
    )
    await make_task(s, p, world.pm.id, status="Done", priority="low", due_date=TODAY)
    await make_task(s, p, world.pm.id, status="Done", priority="low")
    await make_task(s, p, world.pm.id, status="To do", archived_at=datetime.now(UTC))

    stats = await ok(client, world.dev, "GET", stats_path(world))  # project members may read

    counts = {c["status"]["name"]: c["count"] for c in stats["by_status"]}
    assert counts == {
        "Backlog": 0,
        "To do": 2,
        "In progress": 1,
        "Code review": 0,
        "Testing": 0,
        "Blocked": 1,
        "Done": 2,
    }  # the archived task is left out
    assert (stats["total"], stats["open"], stats["completed"]) == (6, 4, 2)
    assert stats["progress_percent"] == 33  # 2 of 6, rounded down
    assert stats["due_this_week"] == 2  # today and Sunday; not next week, not done, not overdue
    assert stats["overdue"] == 1
    assert stats["blocked"] == 1
    assert {p["priority"]: p["count"] for p in stats["by_priority"]} == {
        "highest": 1,
        "high": 1,
        "medium": 2,
        "low": 2,
        "lowest": 0,
    }


async def test_inactive_people_are_not_team_members(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.other_dev.is_active = False
    await session.flush()

    stats = await ok(client, world.pm, "GET", stats_path(world))

    assert stats["team_members"] == 2


async def test_people_outside_the_project_cannot_read_the_stats(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await call(client, world.outsider, "GET", stats_path(world))

    assert response.status_code == 404


# --- several people in the task filter --------------------------------------------------------


async def test_the_task_filter_takes_several_people_and_unassigned(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    p = world.project
    mine = await make_task(session, p, world.pm.id, title="dev", assignee_id=world.dev.id)
    theirs = await make_task(session, p, world.pm.id, title="other", assignee_id=world.other_dev.id)
    lead = await make_task(session, p, world.pm.id, title="pm", assignee_id=world.pm.id)
    nobody = await make_task(session, p, world.pm.id, title="nobody")
    path = f"/projects/{p.id}/tasks"

    async def keys(params: Any) -> set[str]:
        body = await ok(client, world.pm, "GET", path, params=params)
        return {t["key"] for t in body["items"]}

    two = str(world.dev.id), str(world.other_dev.id)
    assert await keys({"assignee_id": two[0]}) == {mine.key}  # one person still works
    assert await keys([("assignee_id", two[0]), ("assignee_id", two[1])]) == {
        mine.key,
        theirs.key,
    }
    assert await keys([("assignee_id", two[0]), ("unassigned", "true")]) == {
        mine.key,
        nobody.key,
    }
    assert await keys({"unassigned": "true"}) == {nobody.key}
    assert lead.key in await keys({})

    board = await ok(
        client,
        world.pm,
        "GET",
        path,
        params=[("view", "board"), ("assignee_id", two[0]), ("assignee_id", two[1])],
    )
    assert board["total"] == 2


async def test_my_tasks_ignore_the_people_filter(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    mine = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    await make_task(session, world.project, world.pm.id, assignee_id=world.other_dev.id)

    body = await ok(
        client, world.dev, "GET", "/me/tasks", params={"assignee_id": str(world.other_dev.id)}
    )

    assert [t["key"] for t in body["items"]] == [mine.key]


# --- editable reporter ------------------------------------------------------------------------


async def test_the_reporter_starts_as_the_creator_and_the_pm_can_change_it(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await ok(
        client, world.pm, "POST", f"/projects/{world.project.id}/tasks", body={"title": "Login"}
    )
    assert created["reporter"]["id"] == str(world.pm.id)

    changed = await ok(
        client,
        world.pm,
        "PATCH",
        f"/tasks/{created['id']}",
        body={"version": created["version"], "reporter_id": str(world.dev.id)},
    )
    log = await ok(client, world.pm, "GET", f"/tasks/{created['id']}/activity")

    assert changed["reporter"]["id"] == str(world.dev.id)
    entry = next(e for e in log["items"] if "reporter" in e["changes"])
    assert entry["changes"]["reporter"] == [world.pm.name, world.dev.name]


async def test_the_reporter_must_be_a_project_member_and_cannot_be_cleared(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id)
    path = f"/tasks/{task.id}"

    outsider = await call(
        client, world.pm, "PATCH", path, {"version": 1, "reporter_id": str(world.outsider.id)}
    )
    cleared = await call(client, world.pm, "PATCH", path, {"version": 1, "reporter_id": None})

    assert outsider.status_code == 422
    assert outsider.json()["error"]["details"][0] == {
        "field": "reporter_id",
        "issue": "not_a_member",
        "message": "The person must be a member of the project.",
    }
    assert cleared.status_code == 422


async def test_developers_cannot_change_the_reporter(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    own = await make_task(session, world.project, world.dev.id, assignee_id=world.dev.id)

    response = await call(
        client,
        world.dev,
        "PATCH",
        f"/tasks/{own.id}",
        {"version": 1, "reporter_id": str(world.other_dev.id)},
    )

    assert response.status_code == 403


async def test_the_reporter_not_the_creator_hears_about_changes(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(
        session,
        world.project,
        world.pm.id,
        assignee_id=world.dev.id,
        reporter_id=world.other_dev.id,
    )

    await ok(
        client,
        world.dev,
        "PATCH",
        f"/tasks/{task.id}",
        body={"version": 1, "status_id": str(await _status_id(session, world, "In progress"))},
    )

    reporter_inbox = await ok(client, world.other_dev, "GET", "/me/notifications")
    creator_inbox = await ok(client, world.pm, "GET", "/me/notifications")
    assert [n["setting"] for n in reporter_inbox["items"]] == ["tasks_reported"]
    assert creator_inbox["items"] == []


async def _status_id(session: AsyncSession, w: World, name: str) -> Any:
    return (await status_by_name(session, w.project.id, name)).id
