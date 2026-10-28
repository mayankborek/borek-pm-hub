"""Dashboard APIs: PM metrics, developer view, permissions, counts match the task lists."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.projects.models import Project, ProjectMember
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def as_user(user: User) -> dict[str, str]:
    return {HEADER: str(user.id)}


async def join(
    session: AsyncSession, project: Project, user: User, role: str = "developer"
) -> None:
    session.add(ProjectMember(project_id=project.id, user_id=user.id, project_role=role))
    await session.flush()


class World:
    pm: User
    dev: User
    other_dev: User
    outsider: User
    alpha: Project
    beta: Project


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    """Alpha (active): dev + other_dev. Beta (planned): other_dev only.

    Alpha tasks: done, in progress (overdue, dev), blocked (dev), to do (other_dev, overdue),
    one archived. Beta: one task for other_dev.
    """
    w = World()
    w.pm = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session)
    w.dev.name = "Dana Dev"
    w.other_dev = await make_user(session)
    w.other_dev.name = "Omar Other"
    w.outsider = await make_user(session)
    w.alpha = await make_project(session, w.pm.id, code="ALP")
    w.alpha.status = "active"
    w.beta = await make_project(session, w.pm.id, code="BET")
    await join(session, w.alpha, w.dev)
    await join(session, w.alpha, w.other_dev)
    await join(session, w.beta, w.other_dev)
    today = date.today()
    await make_task(
        session, w.alpha, w.pm.id, title="Done", status="Done", completed_at=datetime.now(UTC),
        assignee_id=w.dev.id, due_date=today - timedelta(days=9),
    )  # fmt: skip
    await make_task(
        session, w.alpha, w.pm.id, title="Running late", status="In progress",
        assignee_id=w.dev.id, due_date=today - timedelta(days=2),
    )  # fmt: skip
    await make_task(
        session, w.alpha, w.pm.id, title="Stuck", status="Blocked", blocked_reason="waiting",
        blocked_at=datetime.now(UTC), assignee_id=w.dev.id,
    )  # fmt: skip
    await make_task(
        session, w.alpha, w.pm.id, title="Not started", assignee_id=w.other_dev.id,
        due_date=today - timedelta(days=5),
    )  # fmt: skip
    await make_task(
        session, w.alpha, w.pm.id, title="Archived", archived_at=datetime.now(UTC),
        assignee_id=w.dev.id, due_date=today - timedelta(days=1),
    )  # fmt: skip
    await make_task(session, w.beta, w.pm.id, title="Beta work", assignee_id=w.other_dev.id)
    return w


async def test_pm_dashboard_metrics_projects_and_attention(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await client.get("/api/v1/dashboard", headers=as_user(world.pm))

    assert response.status_code == 200
    body = response.json()
    assert (body["active_projects"], body["projects_total"]) == (1, 2)
    assert body["summary"] == {
        "total": 5,  # the archived task is not counted
        "completed": 1,
        "in_progress": 1,
        "blocked": 1,
        "overdue": 2,  # the done task is late but finished
        "completion_percent": 20,
    }
    assert [p["code"] for p in body["projects"]] == ["ALP", "BET"]
    alpha = body["projects"][0]
    assert alpha["status"] == "active" and alpha["tasks"]["total"] == 4
    assert alpha["members"] == []
    assert body["blocked"]["total"] == 1
    assert body["blocked"]["items"][0]["title"] == "Stuck"
    assert body["blocked"]["items"][0]["blocked_reason"] == "waiting"
    assert [t["title"] for t in body["overdue"]["items"]] == ["Not started", "Running late"]
    assert body["overdue"]["items"][0]["assignee"]["name"] == "Omar Other"


async def test_pm_dashboard_matches_the_task_lists_and_follows_changes(
    client: httpx.AsyncClient, world: World
) -> None:
    pm = as_user(world.pm)
    listed = await client.get("/api/v1/tasks", headers=pm, params={"overdue": "true"})
    dash = (await client.get("/api/v1/dashboard", headers=pm)).json()
    assert listed.json()["total"] == dash["overdue"]["total"] == dash["summary"]["overdue"]

    blocked = dash["blocked"]["items"][0]
    done = await client.get(f"/api/v1/projects/{world.alpha.id}/statuses", headers=pm)
    done_id = next(s["id"] for s in done.json() if s["category"] == "done")
    patched = await client.patch(
        f"/api/v1/tasks/{blocked['id']}",
        headers=pm,
        json={"version": blocked["version"], "status_id": done_id},
    )
    assert patched.status_code == 200

    after = (await client.get("/api/v1/dashboard", headers=pm)).json()
    assert after["summary"]["blocked"] == 0 and after["summary"]["completed"] == 2
    assert after["blocked"] == {"total": 0, "items": []}


async def test_attention_lists_respect_limit(client: httpx.AsyncClient, world: World) -> None:
    body = (
        await client.get("/api/v1/dashboard", headers=as_user(world.pm), params={"limit": 1})
    ).json()
    assert body["overdue"]["total"] == 2 and len(body["overdue"]["items"]) == 1
    response = await client.get("/api/v1/dashboard", headers=as_user(world.pm), params={"limit": 0})
    assert response.status_code == 422


async def test_pm_dashboard_is_pm_only(client: httpx.AsyncClient, world: World) -> None:
    assert (await client.get("/api/v1/dashboard", headers=as_user(world.dev))).status_code == 403
    assert (await client.get("/api/v1/dashboard")).status_code == 401


async def test_empty_dashboard(client: httpx.AsyncClient, session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)
    body = (await client.get("/api/v1/dashboard", headers=as_user(pm))).json()
    assert body["projects"] == [] and body["active_projects"] == 0
    assert body["summary"]["total"] == 0 and body["summary"]["completion_percent"] == 0
    assert body["blocked"] == {"total": 0, "items": []}


async def test_archived_projects_are_left_out(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.beta.archived_at = datetime.now(UTC)
    await session.flush()
    body = (await client.get("/api/v1/dashboard", headers=as_user(world.pm))).json()
    assert [p["code"] for p in body["projects"]] == ["ALP"]
    assert body["summary"]["total"] == 4


async def test_developer_dashboard_shows_own_work_and_team_counts(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await client.get("/api/v1/dashboard/me", headers=as_user(world.dev))

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total": 3,
        "completed": 1,
        "in_progress": 1,
        "blocked": 1,
        "overdue": 1,
        "completion_percent": 33,
    }
    assert [p["code"] for p in body["projects"]] == ["ALP"]  # not Beta: not a member
    members = {m["user"]["name"]: m for m in body["projects"][0]["members"]}
    assert set(members) == {"Dana Dev", "Omar Other"}
    assert members["Dana Dev"]["tasks"]["total"] == 3
    assert members["Omar Other"]["tasks"]["overdue"] == 1
    assert [t["title"] for t in body["blocked"]["items"]] == ["Stuck"]
    assert [t["title"] for t in body["overdue"]["items"]] == ["Running late"]


async def test_developer_never_sees_other_projects_in_the_dashboard(
    client: httpx.AsyncClient, world: World
) -> None:
    body = (await client.get("/api/v1/dashboard/me", headers=as_user(world.outsider))).json()
    assert body["summary"]["total"] == 0 and body["projects"] == []
    assert body["overdue"]["items"] == []
    # a member with no tasks still lists the teammates' counts
    other = (await client.get("/api/v1/dashboard/me", headers=as_user(world.other_dev))).json()
    assert [p["code"] for p in other["projects"]] == ["ALP", "BET"]
    assert other["summary"]["total"] == 2


async def test_cancelled_projects_are_left_out_of_dashboards_and_cross_project_lists(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.beta.status = "cancelled"
    await session.flush()
    pm = as_user(world.pm)

    body = (await client.get("/api/v1/dashboard", headers=pm)).json()
    assert [p["code"] for p in body["projects"]] == ["ALP"]
    assert body["projects_total"] == 1 and body["summary"]["total"] == 4

    mine = (await client.get("/api/v1/dashboard/me", headers=as_user(world.other_dev))).json()
    assert [p["code"] for p in mine["projects"]] == ["ALP"]
    assert mine["summary"]["total"] == 1  # "Not started"; the Beta task is hidden

    titles = [t["title"] for t in (await client.get("/api/v1/tasks", headers=pm)).json()["items"]]
    assert "Beta work" not in titles
    my_tasks = await client.get("/api/v1/me/tasks", headers=as_user(world.other_dev))
    assert [t["title"] for t in my_tasks.json()["items"]] == ["Not started"]

    inside = await client.get(f"/api/v1/projects/{world.beta.id}/tasks", headers=pm)
    assert [t["title"] for t in inside.json()["items"]] == ["Beta work"]
    listed = await client.get("/api/v1/projects", headers=pm)
    assert "BET" in [p["code"] for p in listed.json()["items"]]


async def test_reopened_project_returns_to_the_dashboard(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.beta.status = "cancelled"
    await session.flush()
    world.beta.status = "active"
    await session.flush()
    body = (await client.get("/api/v1/dashboard", headers=as_user(world.pm))).json()
    assert [p["code"] for p in body["projects"]] == ["ALP", "BET"]
    assert body["summary"]["total"] == 5


async def test_developer_with_only_completed_tasks_still_sees_their_history(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    finisher = await make_user(session)
    await join(session, world.alpha, finisher)
    for title in ("Shipped login", "Shipped search"):
        await make_task(
            session, world.alpha, world.pm.id, title=title, status="Done",
            completed_at=datetime.now(UTC), assignee_id=finisher.id,
        )  # fmt: skip
    dev = as_user(finisher)

    dash = (await client.get("/api/v1/dashboard/me", headers=dev)).json()
    assert dash["summary"] == {
        "total": 2,
        "completed": 2,
        "in_progress": 0,
        "blocked": 0,
        "overdue": 0,
        "completion_percent": 100,
    }
    assert dash["blocked"]["items"] == [] and dash["overdue"]["items"] == []

    everything = (await client.get("/api/v1/me/tasks", headers=dev)).json()
    assert everything["total"] == 2
    assert {t["title"] for t in everything["items"]} == {"Shipped login", "Shipped search"}

    done = await client.get("/api/v1/me/tasks", headers=dev, params={"category": "done"})
    assert done.json()["total"] == 2
    pending = await client.get(
        "/api/v1/me/tasks",
        headers=dev,
        params=[("category", "todo"), ("category", "in_progress"), ("category", "blocked")],
    )
    assert pending.status_code == 200 and pending.json()["total"] == 0
