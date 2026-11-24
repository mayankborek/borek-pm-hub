"""Sprints (Jira-like): plan, start, complete with spillover, sprint history, backlog."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole, ProjectRole
from app.projects.models import Project, ProjectMember
from app.tasks.models import Task, TaskActivity
from app.users.models import User
from tests.conftest import make_project, make_task, make_user, status_by_name
from tests.test_auth import HEADER, build_app, client_for

API = "/api/v1"
TODAY = datetime.now(UTC).date()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


class World:
    pm: User
    dev: User
    am: User
    project: Project
    other: Project


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.pm = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session, GlobalRole.DEVELOPER)
    w.project = await make_project(session, w.pm.id, "WEB")
    w.other = await make_project(session, w.pm.id, "OTH")
    session.add(
        ProjectMember(project_id=w.project.id, user_id=w.dev.id, project_role=ProjectRole.DEVELOPER)
    )
    await session.commit()
    return w


async def call(
    client: httpx.AsyncClient,
    user: User,
    method: str,
    path: str,
    body: Any = None,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    return await client.request(
        method, API + path, headers={HEADER: str(user.id)}, json=body, params=params
    )


async def ok(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any = None
) -> Any:
    response = await call(client, user, method, path, body)
    assert response.status_code < 300, response.text
    return response.json() if response.content else None


def sp(w: World, rest: str = "") -> str:
    return f"/projects/{w.project.id}/sprints{rest}"


async def new_sprint(client: httpx.AsyncClient, w: World, **body: Any) -> dict[str, Any]:
    return await ok(client, w.pm, "POST", sp(w), body)


async def move(
    client: httpx.AsyncClient, w: World, tasks: list[Task], sprint_id: str | None
) -> int:
    body = {"task_ids": [str(t.id) for t in tasks], "sprint_id": sprint_id}
    return (await ok(client, w.pm, "POST", sp(w, "/move-tasks"), body))["moved"]


async def start(client: httpx.AsyncClient, w: World, sprint: dict[str, Any], **body: Any) -> Any:
    fresh = await ok(client, w.pm, "GET", sp(w, f"/{sprint['id']}"))
    body = {"version": fresh["version"], "start_date": day(0), "end_date": day(13), **body}
    return await call(client, w.pm, "POST", sp(w, f"/{sprint['id']}/start"), body)


async def complete(client: httpx.AsyncClient, w: World, sprint_id: str, **body: Any) -> Any:
    fresh = await ok(client, w.pm, "GET", sp(w, f"/{sprint_id}"))
    return await call(
        client,
        w.pm,
        "POST",
        sp(w, f"/{sprint_id}/complete"),
        {"version": fresh["version"], **body},
    )


async def task_ids_in(client: httpx.AsyncClient, w: World, **params: Any) -> set[str]:
    response = await call(
        client, w.pm, "GET", f"/projects/{w.project.id}/tasks", params={"page_size": 200, **params}
    )
    assert response.status_code == 200, response.text
    return {t["id"] for t in response.json()["items"]}


async def test_new_sprints_get_the_next_number_and_a_default_name(
    client: httpx.AsyncClient, world: World
) -> None:
    first = await new_sprint(client, world)
    second = await new_sprint(client, world, name="Launch", goal="Ship the login page")
    assert (first["number"], first["name"], first["state"]) == (1, "WEB Sprint 1", "planned")
    assert (second["number"], second["name"], second["goal"]) == (
        2,
        "Launch",
        "Ship the login page",
    )
    assert first["counts"] == {"total": 0, "done": 0, "open": 0}
    assert first["report"] is None and first["days_left"] is None


async def test_the_list_shows_active_then_planned_then_newest_completed_10_per_page(
    client: httpx.AsyncClient, world: World
) -> None:
    for _ in range(12):
        await new_sprint(client, world)
    listed = await ok(client, world.pm, "GET", sp(world))
    assert (listed["total"], listed["page_size"], len(listed["items"])) == (12, 10, 10)
    sprints = [s for s in (await ok(client, world.pm, "GET", sp(world) + "?page_size=50"))["items"]]
    s1, s2, s3 = (s for s in sorted(sprints, key=lambda s: s["number"])[:3])
    assert (await start(client, world, s1)).status_code == 200
    assert (await complete(client, world, s1["id"])).status_code == 200
    assert (await start(client, world, s2)).status_code == 200
    assert (await complete(client, world, s2["id"])).status_code == 200
    assert (await start(client, world, s3)).status_code == 200
    order = [
        s["number"]
        for s in (await ok(client, world.pm, "GET", sp(world) + "?page_size=50"))["items"]
    ]
    assert order == [3, *range(4, 13), 2, 1]
    history = await ok(client, world.pm, "GET", sp(world) + "?state=completed")
    assert [s["number"] for s in history["items"]] == [2, 1] and history["total"] == 2


async def test_moving_tasks_into_a_sprint_and_back_to_the_backlog(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    a = await make_task(session, world.project, world.pm.id, title="A")
    b = await make_task(session, world.project, world.pm.id, title="B")
    await session.commit()
    sprint = await new_sprint(client, world)
    assert await move(client, world, [a, b], sprint["id"]) == 2
    assert await move(client, world, [a], sprint["id"]) == 0  # already there
    assert await task_ids_in(client, world, sprint_id=sprint["id"]) == {str(a.id), str(b.id)}
    assert await task_ids_in(client, world, backlog="true") == set()
    task = await ok(client, world.pm, "GET", f"/tasks/{a.id}")
    assert task["sprint_id"] == sprint["id"]
    detail = await ok(client, world.pm, "GET", sp(world, f"/{sprint['id']}"))
    assert {t["key"] for t in detail["tasks"]} == {a.key, b.key}
    assert detail["counts"] == {"total": 2, "done": 0, "open": 2}

    assert await move(client, world, [b], None) == 1
    assert await task_ids_in(client, world, backlog="true") == {str(b.id)}
    history = await session.scalars(
        select(TaskActivity).where(TaskActivity.task_id == b.id).order_by(TaskActivity.created_at)
    )
    assert [r.changes for r in history] == [
        {"sprint": [None, "WEB Sprint 1"]},
        {"sprint": ["WEB Sprint 1", None]},
    ]


async def test_tasks_of_another_project_or_unknown_sprints_are_refused(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    mine = await make_task(session, world.project, world.pm.id)
    theirs = await make_task(session, world.other, world.pm.id)
    await session.commit()
    sprint = await new_sprint(client, world)
    other_sprint = await ok(client, world.pm, "POST", f"/projects/{world.other.id}/sprints", {})
    body = {"task_ids": [str(theirs.id)], "sprint_id": sprint["id"]}
    response = await call(client, world.pm, "POST", sp(world, "/move-tasks"), body)
    assert response.status_code == 422
    body = {"task_ids": [str(mine.id)], "sprint_id": other_sprint["id"]}
    response = await call(client, world.pm, "POST", sp(world, "/move-tasks"), body)
    assert response.status_code == 422
    patch = {"version": mine.version, "sprint_id": other_sprint["id"]}
    response = await call(client, world.pm, "PATCH", f"/tasks/{mine.id}", patch)
    assert response.status_code == 422


async def test_leads_set_the_sprint_on_a_task_developers_cannot(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    await session.commit()
    sprint = await new_sprint(client, world)
    refused = await call(
        client, world.dev, "PATCH", f"/tasks/{task.id}", {"version": 1, "sprint_id": sprint["id"]}
    )
    assert refused.status_code == 403
    created = await call(
        client,
        world.dev,
        "POST",
        f"/projects/{world.project.id}/tasks",
        {"title": "Mine", "sprint_id": sprint["id"]},
    )
    assert created.status_code == 403
    done = await ok(
        client, world.pm, "PATCH", f"/tasks/{task.id}", {"version": 1, "sprint_id": sprint["id"]}
    )
    assert done["sprint_id"] == sprint["id"]
    new = await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.project.id}/tasks",
        {"title": "Planned", "sprint_id": sprint["id"]},
    )
    assert new["sprint_id"] == sprint["id"]
    # Developers still read sprints.
    assert (await call(client, world.dev, "GET", sp(world))).status_code == 200


async def test_starting_needs_dates_and_only_one_sprint_runs_at_a_time(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    a = await make_task(session, world.project, world.pm.id)
    await session.commit()
    first = await new_sprint(client, world)
    second = await new_sprint(client, world)
    await move(client, world, [a], first["id"])
    no_dates = await call(
        client, world.pm, "POST", sp(world, f"/{first['id']}/start"), {"version": first["version"]}
    )
    assert no_dates.status_code == 422
    started = await start(client, world, first, goal="Login")
    assert started.status_code == 200, started.text
    body = started.json()
    assert (body["state"], body["days_left"], body["goal"]) == ("active", 13, "Login")
    assert body["started_by"]["id"] == str(world.pm.id)
    again = await start(client, world, second)
    assert again.status_code == 409 and again.json()["error"]["code"] == "SPRINT_ALREADY_ACTIVE"
    restart = await start(client, world, first)
    assert restart.status_code == 409 and restart.json()["error"]["code"] == "SPRINT_NOT_PLANNED"
    # An active sprint keeps its dates.
    fresh = await ok(client, world.pm, "GET", sp(world, f"/{first['id']}"))
    cleared = await call(
        client,
        world.pm,
        "PATCH",
        sp(world, f"/{first['id']}"),
        {"version": fresh["version"], "end_date": None},
    )
    assert cleared.status_code == 422
    moved = await call(
        client,
        world.pm,
        "PATCH",
        sp(world, f"/{first['id']}"),
        {"version": fresh["version"], "end_date": day(20)},
    )
    assert moved.status_code == 200 and moved.json()["days_left"] == 20


async def test_completing_records_outcomes_and_spills_open_tasks_to_the_backlog(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    done_status = await status_by_name(session, world.project.id, "Done")
    done = await make_task(session, world.project, world.pm.id, title="Done one")
    done.status_id = done_status.id
    open_ = await make_task(session, world.project, world.pm.id, title="Open one")
    await session.commit()
    sprint = await new_sprint(client, world)
    await move(client, world, [done, open_], sprint["id"])
    late = await make_task(session, world.project, world.pm.id, title="Added later")
    await session.commit()
    assert (await start(client, world, sprint)).status_code == 200
    await move(client, world, [late], sprint["id"])

    response = await complete(client, world, sprint["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "completed"
    assert body["report"] == {"committed": 2, "completed": 1, "spilled": 2, "spilled_to": None}
    assert body["counts"] == {"total": 1, "done": 1, "open": 0}  # the done task stays
    assert await task_ids_in(client, world, backlog="true") == {str(open_.id), str(late.id)}

    detail = await ok(client, world.pm, "GET", sp(world, f"/{sprint['id']}"))
    outcomes = {
        t["title"]: (t["outcome"], t["status_name"], t["times_spilled"]) for t in detail["tasks"]
    }
    assert outcomes == {
        "Done one": ("done", "Done", 0),
        "Open one": ("spilled", "To do", 1),
        "Added later": ("spilled", "To do", 1),
    }
    # Completed sprints never change.
    patch = await call(
        client,
        world.pm,
        "PATCH",
        sp(world, f"/{sprint['id']}"),
        {"version": body["version"], "name": "x"},
    )
    assert patch.status_code == 409 and patch.json()["error"]["code"] == "SPRINT_COMPLETED"
    gone = await call(client, world.pm, "DELETE", sp(world, f"/{sprint['id']}"))
    assert gone.status_code == 409
    into = await call(
        client,
        world.pm,
        "POST",
        sp(world, "/move-tasks"),
        {"task_ids": [str(open_.id)], "sprint_id": sprint["id"]},
    )
    assert into.status_code == 422


async def test_spillover_to_a_planned_sprint_or_a_new_one_counts_repeats(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, title="Stubborn")
    await session.commit()
    first = await new_sprint(client, world)
    second = await new_sprint(client, world)
    await move(client, world, [task], first["id"])
    await start(client, world, first)
    wrong = await complete(client, world, first["id"], move_open_tasks_to=first["id"])
    assert wrong.status_code == 422
    response = await complete(client, world, first["id"], move_open_tasks_to=second["id"])
    assert response.json()["report"]["spilled_to"]["id"] == second["id"]
    assert await task_ids_in(client, world, sprint_id=second["id"]) == {str(task.id)}

    await start(client, world, second)
    response = await complete(client, world, second["id"], create_next_sprint=True)
    created = response.json()["report"]["spilled_to"]
    assert (created["number"], created["name"], created["state"]) == (3, "WEB Sprint 3", "planned")
    detail = await ok(client, world.pm, "GET", sp(world, f"/{created['id']}"))
    assert [(t["key"], t["times_spilled"]) for t in detail["tasks"]] == [(task.key, 2)]
    both = await complete(
        client, world, created["id"], move_open_tasks_to=second["id"], create_next_sprint=True
    )
    assert both.status_code == 422


async def test_removing_a_planned_sprint_returns_its_tasks_to_the_backlog(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id)
    await session.commit()
    planned = await new_sprint(client, world)
    active = await new_sprint(client, world)
    await move(client, world, [task], planned["id"])
    await start(client, world, active)
    assert (
        await call(client, world.pm, "DELETE", sp(world, f"/{planned['id']}"))
    ).status_code == 204
    assert (await call(client, world.pm, "GET", sp(world, f"/{planned['id']}"))).status_code == 404
    assert await task_ids_in(client, world, backlog="true") == {str(task.id)}
    refused = await call(client, world.pm, "DELETE", sp(world, f"/{active['id']}"))
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "SPRINT_ACTIVE"
    # The number is never reused.
    assert (await new_sprint(client, world))["number"] == 3


async def test_a_stale_version_is_refused(client: httpx.AsyncClient, world: World) -> None:
    sprint = await new_sprint(client, world)
    await ok(client, world.pm, "PATCH", sp(world, f"/{sprint['id']}"), {"version": 1, "goal": "A"})
    stale = await call(
        client, world.pm, "PATCH", sp(world, f"/{sprint['id']}"), {"version": 1, "goal": "B"}
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"
