"""Developer Role Guide (design handoff November 2026) backend updates: My Work figures and My
Focus, team functions on the Overview, the project card health badge, a notification when an
existing person is put on a project, and the developer's shorter notification settings."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.notifications.models import Notification
from app.projects.models import Project, ProjectMember
from app.reporting.models import StatusReport
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for

API = "/api/v1"
TODAY = datetime.now(UTC).date()
SUNDAY = TODAY + timedelta(days=6 - TODAY.weekday())


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


async def call(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any = None, **kw: Any
) -> httpx.Response:
    return await client.request(method, API + path, headers={HEADER: str(user.id)}, json=body, **kw)


async def ok(client: httpx.AsyncClient, user: User, method: str, path: str, **kw: Any) -> Any:
    response = await call(client, user, method, path, **kw)
    assert response.status_code < 300, response.text
    return response.json() if response.content else None


class World:
    pm: User
    dev: User
    other_dev: User
    project: Project


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.pm = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session)
    w.other_dev = await make_user(session)
    w.project = await make_project(session, w.pm.id, code="DEV")
    for person in (w.dev, w.other_dev):
        session.add(ProjectMember(project_id=w.project.id, user_id=person.id))
    await session.flush()
    return w


# --- My Work ------------------------------------------------------------------------------------


async def test_my_work_counts_due_this_week_and_today_for_my_open_tasks_only(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    p, s, me = world.project, session, world.dev.id
    await make_task(s, p, world.pm.id, assignee_id=me, due_date=TODAY)
    await make_task(s, p, world.pm.id, assignee_id=me, status="In progress", due_date=SUNDAY)
    await make_task(s, p, world.pm.id, assignee_id=me, due_date=SUNDAY + timedelta(days=1))
    await make_task(s, p, world.pm.id, assignee_id=me, status="Done", due_date=TODAY)  # done
    await make_task(s, p, world.pm.id, assignee_id=world.other_dev.id, due_date=TODAY)  # not mine
    await make_task(  # archived
        s, p, world.pm.id, assignee_id=me, due_date=TODAY, archived_at=datetime.now(UTC)
    )

    body = await ok(client, world.dev, "GET", "/dashboard/me")

    assert body["due_today"] == 1
    assert body["due_this_week"] == 2
    assert (body["summary"]["total"], body["summary"]["completed"]) == (4, 1)


async def test_my_focus_puts_work_in_progress_first_then_priority_then_due_date(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    p, s, me = world.project, session, world.dev.id
    later = TODAY + timedelta(days=10)
    await make_task(s, p, world.pm.id, title="todo-highest", assignee_id=me, priority="highest")
    await make_task(s, p, world.pm.id, title="backlog", status="Backlog", assignee_id=me)
    await make_task(
        s, p, world.pm.id, title="blocked", status="Blocked", assignee_id=me, priority="high"
    )
    await make_task(s, p, world.pm.id, title="wip-medium", status="In progress", assignee_id=me)
    await make_task(  # Code review is in progress too
        s,
        p,
        world.pm.id,
        title="review-high-late",
        status="Code review",
        assignee_id=me,
        priority="high",
        due_date=later,
    )
    await make_task(
        s,
        p,
        world.pm.id,
        title="wip-high-soon",
        status="In progress",
        assignee_id=me,
        priority="high",
        due_date=TODAY,
    )
    await make_task(s, p, world.pm.id, title="done", status="Done", assignee_id=me)
    await make_task(s, p, world.pm.id, title="someone else", assignee_id=world.other_dev.id)

    body = await ok(client, world.dev, "GET", "/dashboard/me")
    assert body["focus"]["total"] == 6
    assert [t["title"] for t in body["focus"]["items"]] == [
        "wip-high-soon",
        "review-high-late",
        "wip-medium",
        "blocked",
    ]  # default limit 4

    body = await ok(client, world.dev, "GET", "/dashboard/me", params={"focus_limit": 20})
    assert [t["title"] for t in body["focus"]["items"]][4:] == ["todo-highest", "backlog"]


async def test_my_focus_leaves_out_archived_projects(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    world.project.archived_at = datetime.now(UTC)
    await session.flush()

    body = await ok(client, world.dev, "GET", "/dashboard/me")

    assert body["focus"] == {"total": 0, "items": []}


# --- Overview: team functions -------------------------------------------------------------------


async def test_overview_counts_different_job_titles_of_active_members(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.pm.job_title = "Project Manager"
    world.dev.job_title = "Frontend Developer"
    world.other_dev.job_title = " frontend developer "  # same function, other spelling
    third = await make_user(session)
    third.job_title = "QA"
    third.is_active = False  # deactivated: not in the team
    no_title = await make_user(session)
    for person in (third, no_title):
        session.add(ProjectMember(project_id=world.project.id, user_id=person.id))
    await session.flush()

    stats = await ok(client, world.dev, "GET", f"/projects/{world.project.id}/task-stats")

    assert stats["team_members"] == 4
    assert stats["team_functions"] == 2


# --- project card health ------------------------------------------------------------------------


def _report(project: Project, author: User, rag: str, day: int, *, published: bool) -> StatusReport:
    return StatusReport(
        project_id=project.id,
        rag=rag,
        summary="Summary",
        report_date=date(2026, 11, day),
        state="published" if published else "draft",
        published_at=datetime(2026, 11, day, 12, tzinfo=UTC) if published else None,
        published_by=author.id if published else None,
        created_by=author.id,
    )


async def test_project_list_shows_health_of_the_newest_published_report(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    other = await make_project(session, world.pm.id, code="OTH")
    session.add(ProjectMember(project_id=other.id, user_id=world.dev.id))
    session.add_all(
        [
            _report(world.project, world.pm, "green", 3, published=True),
            _report(world.project, world.pm, "amber", 10, published=True),
            _report(world.project, world.pm, "red", 20, published=False),  # draft: ignored
        ]
    )
    await session.flush()

    body = await ok(client, world.dev, "GET", "/projects")

    health = {p["code"]: p["health"] for p in body["items"]}
    assert health == {"DEV": "at_risk", "OTH": None}


# --- added to a project -------------------------------------------------------------------------


async def _notes(session: AsyncSession, user: User) -> list[Notification]:
    return list(
        await session.scalars(select(Notification).where(Notification.recipient_id == user.id))
    )


async def test_adding_an_existing_developer_notifies_them(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    newcomer = await make_user(session)

    await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.project.id}/members",
        body={"user_id": str(newcomer.id)},
    )

    notes = await _notes(session, newcomer)
    assert [(n.type, n.setting, n.entity_type) for n in notes] == [
        ("project.member_added", "projects", "project")
    ]
    assert notes[0].params == {"code": "DEV", "name": "Test project", "project_role": "developer"}
    listed = await ok(client, newcomer, "GET", "/me/notifications")
    assert [n["type"] for n in listed["items"]] == ["project.member_added"]


async def test_new_project_notifies_its_members_but_not_the_creator(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await ok(
        client,
        world.pm,
        "POST",
        "/projects",
        body={"code": "NEW", "name": "New project", "members": [{"user_id": str(world.dev.id)}]},
    )

    assert [n.type for n in await _notes(session, world.dev)] == ["project.member_added"]
    assert await _notes(session, world.pm) == []


async def test_a_developer_can_mute_project_notifications(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    newcomer = await make_user(session)
    await ok(
        client, newcomer, "PUT", "/me/notification-settings", body={"settings": {"projects": False}}
    )

    await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.project.id}/members",
        body={"user_id": str(newcomer.id)},
    )

    assert await _notes(session, newcomer) == []


# --- developer notification settings ------------------------------------------------------------


async def test_developers_only_get_task_mention_requirement_and_project_settings(
    client: httpx.AsyncClient, world: World
) -> None:
    dev = await ok(client, world.dev, "GET", "/me/notification-settings")
    pm = await ok(client, world.pm, "GET", "/me/notification-settings")

    def keys(body: Any) -> list[str]:
        items = body["settings"] if isinstance(body, dict) else body
        return [s["key"] for s in items]

    assert keys(dev) == ["tasks_assigned", "tasks_reported", "mentions", "requirements", "projects"]
    assert "milestones" in keys(pm) and "projects" in keys(pm)

    response = await call(
        client, world.dev, "PUT", "/me/notification-settings", {"settings": {"reports": False}}
    )
    assert response.status_code == 422
