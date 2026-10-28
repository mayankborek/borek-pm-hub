"""Task APIs (PT-16): create, read, list/board, filter, edit, archive, permissions."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.projects.models import Project, ProjectMember
from app.tasks.models import Task
from app.users.models import User
from tests.conftest import make_project, make_task, make_user, status_by_name
from tests.test_auth import HEADER, build_app, client_for


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def as_user(user: User) -> dict[str, str]:
    return {HEADER: str(user.id)}


def tasks_url(project: Project) -> str:
    return f"/api/v1/projects/{project.id}/tasks"


async def join(
    session: AsyncSession, project: Project, user: User, role: str = "developer"
) -> None:
    session.add(ProjectMember(project_id=project.id, user_id=user.id, project_role=role))
    await session.flush()


class World:
    """A PM, two developers in one project, an outsider and a project with default statuses."""

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
    w.project = await make_project(session, w.pm.id, code="BFL")
    await join(session, w.project, w.dev)
    await join(session, w.project, w.other_dev)
    return w


# --- create -----------------------------------------------------------------------------------


async def test_pm_creates_and_assigns_a_task(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    response = await client.post(
        tasks_url(world.project),
        headers=as_user(world.pm),
        json={
            "title": "  Build login  ",
            "description": "Details",
            "priority": "high",
            "labels": ["Frontend", "frontend", " ui "],
            "start_date": "2026-11-01",
            "due_date": "2026-11-10",
            "assignee_id": str(world.dev.id),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["key"] == "BFL-1"
    assert body["title"] == "Build login"
    assert body["labels"] == ["Frontend", "ui"]  # trimmed, duplicates (any case) removed
    assert body["status"]["name"] == "To do" and body["status"]["category"] == "todo"
    assert body["priority"] == "high" and body["version"] == 1
    assert body["assignee"]["id"] == str(world.dev.id)
    assert body["reporter"]["id"] == str(world.pm.id)
    assert body["project_name"] == "Test project" and "project_code" not in body
    assert "progress" not in body and body["estimate_value"] is None
    assert response.headers["location"] == f"/api/v1/tasks/{body['id']}"


async def test_keys_count_up_per_project_and_are_never_reused(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    headers = as_user(world.pm)
    first = await client.post(tasks_url(world.project), headers=headers, json={"title": "a"})
    second = await client.post(tasks_url(world.project), headers=headers, json={"title": "b"})
    await client.delete(f"/api/v1/tasks/{first.json()['id']}", headers=headers)
    third = await client.post(tasks_url(world.project), headers=headers, json={"title": "c"})

    assert [r.json()["key"] for r in (first, second, third)] == ["BFL-1", "BFL-2", "BFL-3"]


async def test_create_with_explicit_status_and_blocked_reason(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    headers = as_user(world.pm)
    blocked = await status_by_name(session, world.project.id, "Blocked")
    done = await status_by_name(session, world.project.id, "Done")

    no_reason = await client.post(
        tasks_url(world.project), headers=headers, json={"title": "x", "status_id": str(blocked.id)}
    )
    assert no_reason.status_code == 422
    assert no_reason.json()["error"]["details"][0]["field"] == "blocked_reason"

    with_reason = await client.post(
        tasks_url(world.project),
        headers=headers,
        json={"title": "x", "status_id": str(blocked.id), "blocked_reason": "No credentials"},
    )
    assert with_reason.status_code == 201
    assert with_reason.json()["blocked_at"] is not None

    finished = await client.post(
        tasks_url(world.project), headers=headers, json={"title": "y", "status_id": str(done.id)}
    )
    assert finished.json()["completed_at"] is not None


async def test_developer_creates_tasks_only_for_themselves(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    headers = as_user(world.dev)

    own = await client.post(tasks_url(world.project), headers=headers, json={"title": "bug"})
    assert own.status_code == 201
    assert own.json()["assignee"]["id"] == str(world.dev.id)  # unassigned input -> self

    explicit = await client.post(
        tasks_url(world.project),
        headers=headers,
        json={"title": "bug 2", "assignee_id": str(world.dev.id)},
    )
    assert explicit.status_code == 201

    for assignee in (world.other_dev.id, world.pm.id):
        other = await client.post(
            tasks_url(world.project),
            headers=headers,
            json={"title": "x", "assignee_id": str(assignee)},
        )
        assert other.status_code == 403
    assert len((await session.scalars(select(Task.id))).all()) == 2


async def test_outsider_cannot_create_and_is_not_told_the_project_exists(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    response = await client.post(
        tasks_url(world.project), headers=as_user(world.outsider), json={"title": "x"}
    )
    assert response.status_code == 404
    assert (await client.post(tasks_url(world.project), json={"title": "x"})).status_code == 401


async def test_invalid_create_is_rejected_without_saving(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    headers = as_user(world.pm)
    foreign_project = await make_project(session, world.pm.id, code="OTH")
    foreign_status = await status_by_name(session, foreign_project.id, "To do")
    cases = [
        {"title": "   "},
        {},
        {"title": "x", "priority": "urgent"},
        {"title": "x", "progress": 10},  # field was removed
        {"title": "x", "estimate_value": 5},
        {"title": "x", "estimate_unit": "hours"},
        {"title": "x", "estimate_value": 0, "estimate_unit": "hours"},
        {"title": "x", "estimate_value": 5, "estimate_unit": "days"},
        {"title": "x", "start_date": "2026-05-10", "due_date": "2026-05-01"},
        {"title": "x", "labels": [""]},
        {"title": "x", "labels": ["l" * 31]},
        {"title": "x", "labels": [f"l{i}" for i in range(11)]},
        {"title": "x", "unknown": 1},
        {"title": "x", "assignee_id": str(uuid.uuid4())},
        {"title": "x", "status_id": str(foreign_status.id)},  # status of another project
    ]
    for payload in cases:
        response = await client.post(tasks_url(world.project), headers=headers, json=payload)
        assert response.status_code in (404, 422), payload
    assert await session.scalar(select(Task.id)) is None
    await session.refresh(world.project)
    assert world.project.task_counter == 0  # failed creates do not burn key numbers


async def test_archived_project_rejects_new_tasks(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.project.archived_at = datetime.now(UTC)
    await session.flush()
    response = await client.post(
        tasks_url(world.project), headers=as_user(world.pm), json={"title": "x"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROJECT_ARCHIVED"


# --- read -------------------------------------------------------------------------------------


async def test_get_task_by_id(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)

    as_member = await client.get(f"/api/v1/tasks/{task.id}", headers=as_user(world.dev))
    as_pm = await client.get(f"/api/v1/tasks/{task.id}", headers=as_user(world.pm))
    as_outsider = await client.get(f"/api/v1/tasks/{task.id}", headers=as_user(world.outsider))

    assert as_member.status_code == 200 and as_member.json()["key"] == "BFL-1"
    assert as_pm.json() == as_member.json()
    assert as_outsider.status_code == 404
    unknown = await client.get(f"/api/v1/tasks/{uuid.uuid4()}", headers=as_user(world.pm))
    assert unknown.status_code == 404
    assert (
        await client.get("/api/v1/tasks/not-a-uuid", headers=as_user(world.pm))
    ).status_code == 422


async def test_developer_sees_all_tasks_of_their_project(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.project, world.pm.id, assignee_id=world.other_dev.id)
    response = await client.get(tasks_url(world.project), headers=as_user(world.dev))
    assert response.json()["total"] == 1


# --- list, filters, board ---------------------------------------------------------------------


async def seed_tasks(session: AsyncSession, w: World) -> None:
    today = date.today()
    await make_task(
        session,
        w.project,
        w.pm.id,
        title="Login page",
        priority="high",
        assignee_id=w.dev.id,
        due_date=today - timedelta(days=2),
        labels=["frontend"],
    )
    await make_task(
        session,
        w.project,
        w.pm.id,
        title="Report export",
        priority="low",
        status="In progress",
        assignee_id=w.other_dev.id,
        due_date=today + timedelta(days=5),
    )
    await make_task(
        session,
        w.project,
        w.pm.id,
        title="Fix bug",
        priority="highest",
        status="Blocked",
        blocked_reason="waiting",
        blocked_at=datetime.now(UTC),
        labels=["bug", "frontend"],
    )
    await make_task(
        session, w.project, w.pm.id, title="Old idea", status="Done", completed_at=datetime.now(UTC)
    )
    await make_task(session, w.project, w.pm.id, title="Archived", archived_at=datetime.now(UTC))


async def titles(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], **params: object
) -> list[str]:
    response = await client.get(url, headers=headers, params=params)  # type: ignore[arg-type]
    assert response.status_code == 200, response.text
    return [t["title"] for t in response.json()["items"]]


async def test_list_filters_search_and_sort(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await seed_tasks(session, world)
    url, headers = tasks_url(world.project), as_user(world.pm)
    in_progress = await status_by_name(session, world.project.id, "In progress")

    assert sorted(await titles(client, url, headers)) == [
        "Fix bug",
        "Login page",
        "Old idea",
        "Report export",
    ]
    assert await titles(client, url, headers, q="export") == ["Report export"]
    assert await titles(client, url, headers, q="bfl-1") == ["Login page"]  # key search
    assert await titles(client, url, headers, status_id=str(in_progress.id)) == ["Report export"]
    assert sorted(await titles(client, url, headers, category=["todo", "blocked"])) == [
        "Fix bug",
        "Login page",
    ]
    assert await titles(client, url, headers, priority=["highest", "high"], sort="priority") == [
        "Fix bug",
        "Login page",
    ]
    assert await titles(client, url, headers, assignee_id=str(world.dev.id)) == ["Login page"]
    assert sorted(await titles(client, url, headers, unassigned="true")) == ["Fix bug", "Old idea"]
    assert sorted(await titles(client, url, headers, label="frontend")) == ["Fix bug", "Login page"]
    assert await titles(client, url, headers, label="bug") == ["Fix bug"]
    soon = (date.today() + timedelta(days=1)).isoformat()
    assert await titles(client, url, headers, due_before=soon) == ["Login page"]
    ordered = await titles(client, url, headers, sort="due_date")
    assert ordered[:2] == ["Login page", "Report export"]
    assert set(ordered[2:]) == {"Old idea", "Fix bug"}


async def test_pagination_and_limits(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await seed_tasks(session, world)
    headers, url = as_user(world.pm), tasks_url(world.project)

    page = (await client.get(url, headers=headers, params={"page_size": 3, "page": 2})).json()

    assert (page["total"], page["page"], page["page_size"], len(page["items"])) == (4, 2, 3, 1)
    for bad in ({"page_size": 500}, {"page": 0}, {"sort": "title"}, {"priority": "urgent"}):
        assert (await client.get(url, headers=headers, params=bad)).status_code == 422


async def test_archived_tasks_are_pm_only_and_opt_in(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await seed_tasks(session, world)
    url = tasks_url(world.project)

    assert "Archived" in await titles(client, url, as_user(world.pm), include_archived="true")
    assert "Archived" not in await titles(client, url, as_user(world.pm))
    assert "Archived" not in await titles(client, url, as_user(world.dev), include_archived="true")


async def test_board_groups_tasks_by_status_in_project_order(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await seed_tasks(session, world)

    response = await client.get(
        tasks_url(world.project), headers=as_user(world.dev), params={"view": "board"}
    )

    assert response.status_code == 200
    body = response.json()
    assert [c["status"]["name"] for c in body["columns"]] == [
        "Backlog",
        "To do",
        "In progress",
        "Code review",
        "Testing",
        "Blocked",
        "Done",
    ]
    by_name = {c["status"]["name"]: c for c in body["columns"]}
    assert [t["title"] for t in by_name["To do"]["tasks"]] == ["Login page"]
    assert by_name["Blocked"]["total"] == 1 and by_name["Backlog"]["tasks"] == []
    assert body["total"] == 4
    filtered = await client.get(
        tasks_url(world.project),
        headers=as_user(world.dev),
        params={"view": "board", "priority": "low"},
    )
    assert filtered.json()["total"] == 1
    assert (
        await client.get(
            tasks_url(world.project), params={"view": "grid"}, headers=as_user(world.dev)
        )
    ).status_code == 422


async def test_cross_project_list_is_scoped_by_role(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await seed_tasks(session, world)
    hidden = await make_project(session, world.pm.id, code="HID")
    await make_task(session, hidden, world.pm.id, title="Secret")
    archived_project = await make_project(session, world.pm.id, code="OLD")
    await make_task(session, archived_project, world.pm.id, title="In archived project")
    archived_project.archived_at = datetime.now(UTC)
    await session.flush()

    pm_titles = await titles(client, "/api/v1/tasks", as_user(world.pm))
    dev_titles = await titles(client, "/api/v1/tasks", as_user(world.dev))
    scoped = await titles(client, "/api/v1/tasks", as_user(world.pm), project_id=str(hidden.id))

    assert "Secret" in pm_titles and "Login page" in pm_titles
    assert "In archived project" not in pm_titles
    assert "Secret" not in dev_titles and "Login page" in dev_titles
    assert scoped == ["Secret"]
    assert (await client.get("/api/v1/tasks")).status_code == 401
    # the list carries what the dashboard needs
    item = (
        await client.get(
            "/api/v1/tasks",
            headers=as_user(world.pm),
            params={"project_id": str(world.project.id), "q": "login"},
        )
    ).json()["items"][0]
    assert item["project_name"] == "Test project" and item["status"]["category"] == "todo"


# --- update -----------------------------------------------------------------------------------


async def test_pm_edits_every_field(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id)
    review = await status_by_name(session, world.project.id, "Code review")

    response = await client.patch(
        f"/api/v1/tasks/{task.id}",
        headers=as_user(world.pm),
        json={
            "version": 1,
            "title": "New title",
            "description": "More",
            "priority": "highest",
            "labels": ["a", "b"],
            "start_date": "2026-11-01",
            "due_date": "2026-11-09",
            "estimate_value": 4,
            "estimate_unit": "hours",
            "assignee_id": str(world.dev.id),
            "status_id": str(review.id),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["title"], body["priority"], body["labels"]) == (
        "New title",
        "highest",
        ["a", "b"],
    )
    assert (body["estimate_value"], body["estimate_unit"]) == (4, "hours")
    assert body["status"]["name"] == "Code review" and body["assignee"]["id"] == str(world.dev.id)
    assert body["version"] == 2
    assert body["updated_at"] >= body["created_at"]


async def test_pm_can_unassign_and_clear_optional_fields(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(
        session,
        world.project,
        world.pm.id,
        assignee_id=world.dev.id,
        due_date=date(2026, 12, 1),
        description="x",
    )
    response = await client.patch(
        f"/api/v1/tasks/{task.id}",
        headers=as_user(world.pm),
        json={"version": 1, "assignee_id": None, "due_date": None, "description": None},
    )
    body = response.json()
    assert response.status_code == 200
    assert (body["assignee"], body["due_date"], body["description"]) == (None, None, None)


async def test_stale_version_gets_409(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id)
    first = await client.patch(
        f"/api/v1/tasks/{task.id}", headers=as_user(world.pm), json={"version": 1, "title": "A"}
    )
    stale = await client.patch(
        f"/api/v1/tasks/{task.id}", headers=as_user(world.pm), json={"version": 1, "title": "B"}
    )
    assert first.status_code == 200
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"


async def test_invalid_updates_are_rejected_and_nothing_changes(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, start_date=date(2026, 5, 10))
    other = await make_project(session, world.pm.id, code="OTH")
    foreign = await status_by_name(session, other.id, "To do")
    cases: list[dict[str, Any]] = [
        {"title": None},
        {"title": " "},
        {"priority": None},
        {"labels": None},
        {"status_id": None},
        {"progress": 10},  # field was removed
        {"estimate_value": 5},  # amount without a unit
        {"estimate_unit": "hours"},
        {"estimate_value": 5, "estimate_unit": "days"},
        {"due_date": "2026-05-01"},
        {"code": "X"},
        {"assignee_id": str(uuid.uuid4())},
        {"status_id": str(foreign.id)},
    ]
    for payload in cases:
        response = await client.patch(
            f"/api/v1/tasks/{task.id}", headers=as_user(world.pm), json={"version": 1, **payload}
        )
        assert response.status_code in (404, 422), payload
    assert (
        await client.patch(
            f"/api/v1/tasks/{task.id}", headers=as_user(world.pm), json={"title": "x"}
        )
    ).status_code == 422
    await session.refresh(task)
    assert task.version == 1 and task.title == "A task"


async def test_blocked_status_rules(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    blocked = await status_by_name(session, world.project.id, "Blocked")
    progress = await status_by_name(session, world.project.id, "In progress")
    url, headers = f"/api/v1/tasks/{task.id}", as_user(world.dev)

    no_reason = await client.patch(
        url, headers=headers, json={"version": 1, "status_id": str(blocked.id)}
    )
    assert no_reason.status_code == 422

    blank = await client.patch(
        url,
        headers=headers,
        json={"version": 1, "status_id": str(blocked.id), "blocked_reason": "  "},
    )
    assert blank.status_code == 422

    entered = await client.patch(
        url,
        headers=headers,
        json={"version": 1, "status_id": str(blocked.id), "blocked_reason": " No API key "},
    )
    assert entered.status_code == 200
    assert entered.json()["blocked_reason"] == "No API key" and entered.json()["blocked_at"]

    reworded = await client.patch(
        url, headers=headers, json={"version": 2, "blocked_reason": "Still waiting"}
    )
    assert reworded.json()["blocked_reason"] == "Still waiting"

    left = await client.patch(
        url, headers=headers, json={"version": 3, "status_id": str(progress.id)}
    )
    assert left.status_code == 200
    assert left.json()["blocked_reason"] is None and left.json()["blocked_at"] is None


async def test_completed_at_follows_done_statuses(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    done = await status_by_name(session, world.project.id, "Done")
    todo = await status_by_name(session, world.project.id, "To do")
    url, headers = f"/api/v1/tasks/{task.id}", as_user(world.dev)

    finished = await client.patch(
        url, headers=headers, json={"version": 1, "status_id": str(done.id)}
    )
    reopened = await client.patch(
        url, headers=headers, json={"version": 2, "status_id": str(todo.id)}
    )

    assert finished.json()["completed_at"] is not None
    assert reopened.json()["completed_at"] is None


async def test_pm_creates_in_backlog_then_moves_task_to_the_board(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    backlog = await status_by_name(session, world.project.id, "Backlog")
    todo = await status_by_name(session, world.project.id, "To do")
    other = await make_project(session, world.pm.id, code="OTH")
    foreign = await status_by_name(session, other.id, "To do")
    headers = as_user(world.pm)

    created = await client.post(
        tasks_url(world.project),
        headers=headers,
        json={"title": "Later", "status_id": str(backlog.id)},
    )
    assert created.status_code == 201
    task = created.json()
    assert task["status"]["category"] == "backlog" and task["assignee"] is None
    url = f"/api/v1/tasks/{task['id']}"

    stale = await client.patch(url, headers=headers, json={"version": 9, "status_id": str(todo.id)})
    wrong_project = await client.patch(
        url, headers=headers, json={"version": 1, "status_id": str(foreign.id)}
    )
    assert (stale.status_code, wrong_project.status_code) == (409, 404)

    # An unassigned backlog task is PM-only: a developer cannot move it.
    denied = await client.patch(
        url, headers=as_user(world.dev), json={"version": 1, "status_id": str(todo.id)}
    )
    assert denied.status_code == 403

    moved = await client.patch(url, headers=headers, json={"version": 1, "status_id": str(todo.id)})
    assert moved.status_code == 200
    assert moved.json()["status"]["name"] == "To do" and moved.json()["version"] == 2

    assert (await client.get(url, headers=headers)).json()["status"]["name"] == "To do"
    board = await client.get(tasks_url(world.project), headers=headers, params={"view": "board"})
    by_name = {c["status"]["name"]: c for c in board.json()["columns"]}
    assert by_name["Backlog"]["tasks"] == []
    assert [t["title"] for t in by_name["To do"]["tasks"]] == ["Later"]


async def test_developer_updates_status_on_own_task_only(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    mine = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    theirs = await make_task(session, world.project, world.pm.id, assignee_id=world.other_dev.id)
    nobody = await make_task(session, world.project, world.pm.id)
    review = await status_by_name(session, world.project.id, "Code review")
    payload = {"version": 1, "status_id": str(review.id)}
    headers = as_user(world.dev)

    ok = await client.patch(f"/api/v1/tasks/{mine.id}", headers=headers, json=payload)
    assert ok.status_code == 200 and ok.json()["status"]["name"] == "Code review"
    for other in (theirs, nobody):
        denied = await client.patch(f"/api/v1/tasks/{other.id}", headers=headers, json=payload)
        assert denied.status_code == 403
    outsider = await client.patch(
        f"/api/v1/tasks/{mine.id}", headers=as_user(world.outsider), json={**payload, "version": 2}
    )
    assert outsider.status_code == 404


async def test_developer_cannot_edit_pm_fields_or_archive(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    own = await make_task(session, world.project, world.dev.id, assignee_id=world.dev.id)
    headers = as_user(world.dev)

    for payload in (
        {"title": "x"},
        {"description": "x"},
        {"labels": ["x"]},
        {"estimate_value": 5, "estimate_unit": "hours"},
        {"assignee_id": str(world.other_dev.id)},
        {"assignee_id": None},
        {"title": "x", "estimate_value": 5, "estimate_unit": "hours"},  # mixed: PM-only part
    ):
        response = await client.patch(
            f"/api/v1/tasks/{own.id}", headers=headers, json={"version": 1, **payload}
        )
        assert response.status_code == 403, payload
    assert (await client.delete(f"/api/v1/tasks/{own.id}", headers=headers)).status_code == 403
    await session.refresh(own)
    assert own.version == 1 and own.archived_at is None


async def test_developer_changes_priority_only_of_tasks_assigned_to_them(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    mine = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    theirs = await make_task(session, world.project, world.pm.id, assignee_id=world.other_dev.id)
    nobody = await make_task(session, world.project, world.pm.id)
    headers = as_user(world.dev)

    ok = await client.patch(
        f"/api/v1/tasks/{mine.id}", headers=headers, json={"version": 1, "priority": "lowest"}
    )
    assert ok.status_code == 200 and ok.json()["priority"] == "lowest"
    for other in (theirs, nobody):
        denied = await client.patch(
            f"/api/v1/tasks/{other.id}", headers=headers, json={"version": 1, "priority": "high"}
        )
        assert denied.status_code == 403
        await session.refresh(other)
        assert other.priority == "medium" and other.version == 1
    mixed = await client.patch(
        f"/api/v1/tasks/{mine.id}",
        headers=headers,
        json={"version": 2, "priority": "high", "title": "renamed"},
    )
    assert mixed.status_code == 403  # the PM-only part blocks the whole request
    outsider = await client.patch(
        f"/api/v1/tasks/{mine.id}",
        headers=as_user(world.outsider),
        json={"version": 2, "priority": "high"},
    )
    assert outsider.status_code == 404


async def test_developer_edits_dates_only_of_tasks_created_for_themselves(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    mine = await make_task(session, world.project, world.dev.id, assignee_id=world.dev.id)
    by_pm = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    unassigned = await make_task(session, world.project, world.dev.id)
    headers = as_user(world.dev)
    dates = {"start_date": "2026-12-01", "due_date": "2026-12-31"}

    ok = await client.patch(
        f"/api/v1/tasks/{mine.id}", headers=headers, json={"version": 1, **dates}
    )
    assert ok.status_code == 200 and ok.json()["due_date"] == "2026-12-31"

    for task in (by_pm, unassigned):
        response = await client.patch(
            f"/api/v1/tasks/{task.id}", headers=headers, json={"version": 1, **dates}
        )
        assert response.status_code == 403
    mixed = await client.patch(
        f"/api/v1/tasks/{mine.id}",
        headers=headers,
        json={"version": 2, "due_date": "2026-12-30", "title": "x"},
    )
    assert mixed.status_code == 403  # the title is still PM-only


async def test_archived_task_cannot_be_edited(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, archived_at=datetime.now(UTC))
    response = await client.patch(
        f"/api/v1/tasks/{task.id}", headers=as_user(world.pm), json={"version": 1, "title": "x"}
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "TASK_ARCHIVED"


# --- archive ----------------------------------------------------------------------------------


async def test_pm_archives_a_task(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    url = f"/api/v1/tasks/{task.id}"

    assert (await client.delete(url, headers=as_user(world.pm))).status_code == 204
    assert (await client.delete(url, headers=as_user(world.pm))).status_code == 204  # idempotent

    await session.refresh(task)
    assert task.archived_at is not None  # kept in the database
    assert (await client.get(url, headers=as_user(world.pm))).status_code == 200
    assert (await client.get(url, headers=as_user(world.dev))).status_code == 404
    assert await titles(client, tasks_url(world.project), as_user(world.pm)) == []
    assert (
        await client.delete(f"/api/v1/tasks/{uuid.uuid4()}", headers=as_user(world.pm))
    ).status_code == 404


async def test_removed_member_loses_access_to_their_tasks(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    removed = await client.delete(
        f"/api/v1/projects/{world.project.id}/members/{world.dev.id}", headers=as_user(world.pm)
    )
    assert removed.status_code == 204
    assert (
        await client.get(f"/api/v1/tasks/{task.id}", headers=as_user(world.dev))
    ).status_code == 404
    body = (await client.get(f"/api/v1/tasks/{task.id}", headers=as_user(world.pm))).json()
    assert body["assignee"] is None


# --- assignment and My Work (PT-17) -----------------------------------------------------------


def assignee_url(task: Task) -> str:
    return f"/api/v1/tasks/{task.id}/assignee"


async def test_pm_assigns_reassigns_and_unassigns(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id)
    pm = as_user(world.pm)

    first = await client.put(
        assignee_url(task), headers=pm, json={"version": 1, "assignee_id": str(world.dev.id)}
    )
    again = await client.put(  # same assignee: accepted, nothing changes
        assignee_url(task), headers=pm, json={"version": 2, "assignee_id": str(world.dev.id)}
    )
    moved = await client.put(
        assignee_url(task), headers=pm, json={"version": 2, "assignee_id": str(world.other_dev.id)}
    )
    cleared = await client.put(
        assignee_url(task), headers=pm, json={"version": 3, "assignee_id": None}
    )

    assert first.status_code == 200 and first.json()["assignee"]["id"] == str(world.dev.id)
    assert again.status_code == 200 and again.json()["version"] == 2
    assert moved.json()["assignee"]["id"] == str(world.other_dev.id)
    assert cleared.json()["assignee"] is None and cleared.json()["version"] == 4


async def test_assignee_must_be_an_active_user(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id)
    inactive = await make_user(session)
    inactive.is_active = False
    await session.flush()

    for bad in (inactive.id, uuid.uuid4()):
        response = await client.put(
            assignee_url(task),
            headers=as_user(world.pm),
            json={"version": 1, "assignee_id": str(bad)},
        )
        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["issue"] == "unknown_user"
    await session.refresh(task)
    assert task.assignee_id is None and task.version == 1
    assert await member_ids(session, world.project) == {world.dev.id, world.other_dev.id}


async def member_ids(session: AsyncSession, project: Project) -> set[uuid.UUID]:
    rows = await session.scalars(
        select(ProjectMember.user_id).where(ProjectMember.project_id == project.id)
    )
    return set(rows)


async def test_assigning_a_non_member_is_refused_and_adds_nobody(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    headers = as_user(world.pm)
    outsider = await make_user(session)
    before = await member_ids(session, world.project)
    task = await make_task(session, world.project, world.pm.id)

    put = await client.put(
        assignee_url(task), headers=headers, json={"version": 1, "assignee_id": str(outsider.id)}
    )
    created = await client.post(
        tasks_url(world.project),
        headers=headers,
        json={"title": "x", "assignee_id": str(outsider.id)},
    )
    patched = await client.patch(
        f"/api/v1/tasks/{task.id}",
        headers=headers,
        json={"version": 1, "assignee_id": str(outsider.id)},
    )

    for response in (put, created, patched):
        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["issue"] == "not_a_member"
    assert await member_ids(session, world.project) == before  # nobody was added


async def test_a_member_added_later_can_be_assigned(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    headers = as_user(world.pm)
    newcomer = await make_user(session)
    task = await make_task(session, world.project, world.pm.id)
    added = await client.post(
        f"/api/v1/projects/{world.project.id}/members",
        headers=headers,
        json={"user_id": str(newcomer.id), "project_role": "developer"},
    )
    assert added.status_code == 201

    put = await client.put(
        assignee_url(task), headers=headers, json={"version": 1, "assignee_id": str(newcomer.id)}
    )
    assert put.status_code == 200 and put.json()["assignee"]["id"] == str(newcomer.id)


async def test_assigning_an_existing_member_does_not_add_a_second_row(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id)
    response = await client.put(
        assignee_url(task),
        headers=as_user(world.pm),
        json={"version": 1, "assignee_id": str(world.dev.id)},
    )
    assert response.status_code == 200
    assert await member_ids(session, world.project) == {world.dev.id, world.other_dev.id}


async def test_assignment_needs_pm_and_current_version(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    body = {"version": 1, "assignee_id": str(world.dev.id)}
    pm = as_user(world.pm)

    as_dev = await client.put(assignee_url(task), headers=as_user(world.dev), json=body)
    as_outsider = await client.put(assignee_url(task), headers=as_user(world.outsider), json=body)
    anonymous = await client.put(assignee_url(task), json=body)
    stale = await client.put(
        assignee_url(task), headers=pm, json={"version": 9, "assignee_id": str(world.other_dev.id)}
    )
    missing = await client.put(f"/api/v1/tasks/{uuid.uuid4()}/assignee", headers=pm, json=body)
    extra = await client.put(assignee_url(task), headers=pm, json={**body, "priority": "low"})

    assert as_dev.status_code == 403  # developers cannot self-assign existing tasks
    assert as_outsider.status_code == 404
    assert anonymous.status_code == 401
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert missing.status_code == 404
    assert extra.status_code == 422


async def test_archived_task_cannot_be_assigned(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, archived_at=datetime.now(UTC))
    response = await client.put(
        assignee_url(task),
        headers=as_user(world.pm),
        json={"version": 1, "assignee_id": str(world.dev.id)},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "TASK_ARCHIVED"


async def test_my_tasks_lists_only_my_assigned_tasks_across_projects(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await seed_tasks(session, world)  # "Login page" is the only one assigned to dev
    second = await make_project(session, world.pm.id, code="SEC")
    await join(session, second, world.dev)
    await make_task(session, second, world.pm.id, title="Second project", assignee_id=world.dev.id)
    await make_task(
        session,
        second,
        world.pm.id,
        title="Archived",
        assignee_id=world.dev.id,
        archived_at=datetime.now(UTC),
    )
    # assigned to the developer, but in a project they are not a member of
    hidden = await make_project(session, world.pm.id, code="HID")
    await make_task(session, hidden, world.pm.id, title="Not mine now", assignee_id=world.dev.id)

    url = "/api/v1/me/tasks"
    mine = await titles(client, url, as_user(world.dev))
    spoof = await titles(client, url, as_user(world.dev), assignee_id=str(world.other_dev.id))
    unassigned = await titles(client, url, as_user(world.dev), unassigned="true")

    assert set(mine) == {"Login page", "Second project"}
    assert spoof == mine and unassigned == mine  # the assignee filters cannot show others' work
    assert await titles(client, url, as_user(world.pm)) == []
    assert (await client.get(url)).status_code == 401


async def test_my_tasks_filters_and_sorting(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    today = date.today()
    await make_task(
        session,
        world.project,
        world.pm.id,
        title="Overdue",
        priority="low",
        due_date=today - timedelta(days=3),
        assignee_id=world.dev.id,
    )
    await make_task(
        session,
        world.project,
        world.pm.id,
        title="Late but done",
        status="Done",
        completed_at=datetime.now(UTC),
        due_date=today - timedelta(days=3),
        assignee_id=world.dev.id,
    )
    await make_task(
        session,
        world.project,
        world.pm.id,
        title="Soon",
        priority="highest",
        status="In progress",
        due_date=today + timedelta(days=2),
        assignee_id=world.dev.id,
    )
    await make_task(
        session,
        world.project,
        world.pm.id,
        title="Stuck",
        priority="high",
        status="Blocked",
        blocked_reason="waiting",
        blocked_at=datetime.now(UTC),
        assignee_id=world.dev.id,
    )
    url, dev = "/api/v1/me/tasks", as_user(world.dev)
    in_progress = await status_by_name(session, world.project.id, "In progress")

    assert await titles(client, url, dev, sort="priority") == [
        "Soon",
        "Stuck",
        "Late but done",
        "Overdue",
    ]
    assert await titles(client, url, dev, overdue="true") == ["Overdue"]  # done is not overdue
    assert await titles(client, url, dev, category="blocked") == ["Stuck"]
    assert await titles(client, url, dev, status_id=str(in_progress.id)) == ["Soon"]
    assert await titles(client, url, dev, due_after=str(today)) == ["Soon"]
    assert await titles(client, url, dev, project_id=str(uuid.uuid4())) == []
    by_due = await titles(client, url, dev)  # default sort: due date, no date last
    assert by_due[-1] == "Stuck" and by_due[-2] == "Soon"


async def test_reassignment_shows_up_in_my_tasks_and_for_the_pm(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(
        session, world.project, world.pm.id, title="Moving", assignee_id=world.dev.id
    )
    url = "/api/v1/me/tasks"
    assert await titles(client, url, as_user(world.dev)) == ["Moving"]

    await client.put(
        assignee_url(task),
        headers=as_user(world.pm),
        json={"version": 1, "assignee_id": str(world.other_dev.id)},
    )
    assert await titles(client, url, as_user(world.dev)) == []
    assert await titles(client, url, as_user(world.other_dev)) == ["Moving"]

    review = await status_by_name(session, world.project.id, "Code review")
    await client.patch(
        f"/api/v1/tasks/{task.id}",
        headers=as_user(world.other_dev),
        json={"version": 2, "status_id": str(review.id)},
    )
    seen = (await client.get(f"/api/v1/tasks/{task.id}", headers=as_user(world.pm))).json()
    assert seen["status"]["name"] == "Code review"
    assert seen["assignee"]["id"] == str(world.other_dev.id)


async def test_five_priority_levels_sort_from_highest_to_lowest(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    for title, priority in (
        ("L", "low"),
        ("LL", "lowest"),
        ("M", "medium"),
        ("HH", "highest"),
        ("H", "high"),
    ):
        await make_task(session, world.project, world.pm.id, title=title, priority=priority)
    url, headers = tasks_url(world.project), as_user(world.pm)

    assert await titles(client, url, headers, sort="priority") == ["HH", "H", "M", "L", "LL"]
    assert await titles(client, url, headers, priority=["lowest"]) == ["LL"]

    created = await client.post(url, headers=headers, json={"title": "New", "priority": "lowest"})
    assert created.status_code == 201 and created.json()["priority"] == "lowest"
    old_name = await client.post(
        url, headers=headers, json={"title": "Old", "priority": "critical"}
    )
    assert old_name.status_code == 422
