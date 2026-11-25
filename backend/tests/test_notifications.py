"""In-app notifications: who gets what (tasks like Jira, change requests, reports, milestones,
requirements), never the actor, settings, reading, access re-checks and the 90-day cleanup."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole, ProjectRole
from app.notifications.models import Notification
from app.notifications.service import delete_old
from app.organisations.models import Organisation, OrganisationAccountManager
from app.projects.models import Project, ProjectMember
from app.users.models import User
from tests.conftest import make_project, make_user, status_by_name
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
    dev2: User
    am: User
    contact: User
    other_contact: User
    admin: User
    project: Project


async def call(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any = None
) -> httpx.Response:
    return await client.request(method, API + path, headers={HEADER: str(user.id)}, json=body)


async def ok(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any = None
) -> Any:
    response = await call(client, user, method, path, body)
    assert response.status_code < 300, response.text
    return response.json() if response.content else None


async def inbox(client: httpx.AsyncClient, user: User) -> list[dict[str, Any]]:
    """Newest first."""
    body = await ok(client, user, "GET", "/me/notifications?limit=50")
    items: list[dict[str, Any]] = body["items"]
    return items


async def types(client: httpx.AsyncClient, user: User) -> list[str]:
    return [n["type"] for n in await inbox(client, user)]


async def unread(client: httpx.AsyncClient, user: User) -> int:
    value: int = (await ok(client, user, "GET", "/me/notifications/unread-count"))["unread"]
    return value


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    acme = Organisation(name="Acme", type="client")
    globex = Organisation(name="Globex", type="client")
    session.add_all([acme, globex])
    await session.flush()
    w.pm = await make_user(session, GlobalRole.PM, email="pm@borek.example")
    w.dev = await make_user(session, GlobalRole.DEVELOPER, email="dev@borek.example")
    w.dev2 = await make_user(session, GlobalRole.DEVELOPER, email="dev2@borek.example")
    w.am = await make_user(session, GlobalRole.ACCOUNT_MANAGER, email="am@borek.example")
    w.admin = await make_user(session, GlobalRole.ADMIN, email="admin@borek.example")
    w.contact = await make_user(session, GlobalRole.CLIENT, email="jordan@acme.example")
    w.contact.organisation_id = acme.id
    w.other_contact = await make_user(session, GlobalRole.CLIENT, email="sam@globex.example")
    w.other_contact.organisation_id = globex.id
    session.add(OrganisationAccountManager(organisation_id=acme.id, user_id=w.am.id))
    w.project = await make_project(session, w.pm.id, "WEB")
    w.project.project_type = "external"
    w.project.client_organisation_id = acme.id
    for dev in (w.dev, w.dev2):
        session.add(
            ProjectMember(
                project_id=w.project.id, user_id=dev.id, project_role=ProjectRole.DEVELOPER
            )
        )
    await session.commit()
    return w


async def new_task(client: httpx.AsyncClient, w: World, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = await ok(
        client, w.pm, "POST", f"/projects/{w.project.id}/tasks", {"title": "Login page", **extra}
    )
    return result


async def patch_task(
    client: httpx.AsyncClient, user: User, task: dict[str, Any], **changes: Any
) -> dict[str, Any]:
    current = await ok(client, user, "GET", f"/tasks/{task['id']}")
    result: dict[str, Any] = await ok(
        client, user, "PATCH", f"/tasks/{task['id']}", {"version": current["version"], **changes}
    )
    return result


# --- tasks --------------------------------------------------------------------------------------


async def test_assigning_a_task_tells_the_assignee_not_the_actor(
    client: httpx.AsyncClient, world: World
) -> None:
    task = await new_task(client, world, assignee_id=str(world.dev.id))

    items = await inbox(client, world.dev)

    assert [n["type"] for n in items] == ["task.assigned"]
    n = items[0]
    assert (n["entity_type"], n["entity_id"], n["setting"]) == (
        "task",
        task["id"],
        "tasks_assigned",
    )
    assert n["params"] == {"key": task["key"], "title": "Login page"}
    assert n["project"]["code"] == "WEB"
    assert n["actor"] == {"id": str(world.pm.id), "name": world.pm.name}
    assert n["read_at"] is None
    assert await inbox(client, world.pm) == []
    assert await unread(client, world.dev) == 1


async def test_one_save_is_one_notification_naming_every_field(
    client: httpx.AsyncClient, world: World
) -> None:
    task = await new_task(client, world, assignee_id=str(world.dev.id))

    await patch_task(client, world.pm, task, title="Login", due_date=day(3))
    await patch_task(
        client,
        world.dev,
        task,
        status_id=str(
            (await ok(client, world.dev, "GET", f"/projects/{world.project.id}/statuses"))[2]["id"]
        ),
    )

    dev_items = await inbox(client, world.dev)
    assert dev_items[0]["type"] == "task.updated"
    assert dev_items[0]["params"]["fields"] == ["due_date", "title"]
    assert dev_items[0]["params"]["title"] == "Login"
    pm_items = await inbox(client, world.pm)  # the creator hears about the developer's change
    assert [n["type"] for n in pm_items] == ["task.updated"]
    assert pm_items[0]["params"]["fields"] == ["status"]
    assert pm_items[0]["params"]["status"]
    assert pm_items[0]["setting"] == "tasks_reported"


async def test_reassigning_tells_the_new_and_the_old_assignee(
    client: httpx.AsyncClient, world: World
) -> None:
    task = await new_task(client, world, assignee_id=str(world.dev.id))
    current = await ok(client, world.pm, "GET", f"/tasks/{task['id']}")

    await ok(
        client,
        world.pm,
        "PUT",
        f"/tasks/{task['id']}/assignee",
        {"assignee_id": str(world.dev2.id), "version": current["version"]},
    )

    assert await types(client, world.dev2) == ["task.assigned"]
    assert await types(client, world.dev) == ["task.unassigned", "task.assigned"]


async def test_a_blocked_task_tells_the_project_leads(
    client: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    task = await new_task(client, world, assignee_id=str(world.dev.id))
    blocked = await status_by_name(session, world.project.id, "Blocked")

    await patch_task(
        client, world.dev, task, status_id=str(blocked.id), blocked_reason="Waiting for the API"
    )

    pm_items = await inbox(client, world.pm)
    by_type = {n["type"]: n for n in pm_items}
    assert set(by_type) == {"task.blocked", "task.updated"}
    assert by_type["task.blocked"]["setting"] == "blocked_tasks"
    assert by_type["task.blocked"]["params"]["reason"] == "Waiting for the API"


async def test_mentions_and_comments(client: httpx.AsyncClient, world: World) -> None:
    task = await new_task(client, world, assignee_id=str(world.dev.id))
    comment = await ok(
        client,
        world.dev,
        "POST",
        f"/tasks/{task['id']}/comments",
        {"body": "Can you check this?", "mention_ids": [str(world.dev2.id)]},
    )

    assert await types(client, world.dev2) == ["task.mentioned"]
    assert await types(client, world.pm) == ["task.commented"]  # the creator
    assert (await inbox(client, world.dev2))[0]["params"]["comment_id"] == comment["id"]

    await ok(
        client,
        world.dev,
        "PATCH",
        f"/tasks/{task['id']}/comments/{comment['id']}",
        {"body": "Can you both check?", "mention_ids": [str(world.dev2.id), str(world.pm.id)]},
    )

    assert await types(client, world.pm) == ["task.mentioned", "task.commented"]
    assert await types(client, world.dev2) == ["task.mentioned"]  # not mentioned twice


async def test_a_new_attachment_tells_assignee_and_creator(
    client: httpx.AsyncClient, world: World
) -> None:
    task = await new_task(client, world, assignee_id=str(world.dev.id))

    await ok(
        client,
        world.pm,
        "POST",
        f"/tasks/{task['id']}/attachments/link",
        {"url": "https://example.com/spec", "name": "Spec"},
    )

    items = await inbox(client, world.dev)
    assert items[0]["type"] == "task.attachment_added"
    assert items[0]["params"]["name"] == "Spec"


# --- change requests, reports, milestones, requirements -----------------------------------------


async def test_change_request_flow(client: httpx.AsyncClient, world: World) -> None:
    raised = await ok(
        client,
        world.contact,
        "POST",
        f"/client/projects/{world.project.id}/change-requests",
        {"title": "New page", "description": "Please add it"},
    )
    path = f"/projects/{world.project.id}/change-requests/{raised['id']}"

    assert await types(client, world.pm) == ["change_request.submitted"]
    assert await types(client, world.am) == ["change_request.submitted"]
    assert await types(client, world.dev) == []  # developers are not part of change requests
    assert await inbox(client, world.contact) == []  # the actor

    reviewed = await ok(client, world.pm, "POST", f"{path}/start-review", {"version": 1})
    await ok(client, world.pm, "POST", f"{path}/comments", {"body": "Note", "internal": True})
    await ok(client, world.pm, "POST", f"{path}/comments", {"body": "We look at it"})
    await ok(
        client,
        world.pm,
        "POST",
        f"{path}/decision",
        {"version": reviewed["version"], "decision": "approved", "note": "Fine"},
    )

    client_items = await inbox(client, world.contact)
    assert [n["type"] for n in client_items] == [
        "change_request.decided",
        "change_request.commented",
        "change_request.review_started",
    ]
    assert client_items[0]["params"]["decision"] == "approved"
    assert client_items[1]["params"]["internal"] is False
    assert "change_request.commented" in await types(client, world.am)
    am_comments = [n for n in await inbox(client, world.am) if n["type"].endswith("commented")]
    assert [n["params"]["internal"] for n in am_comments] == [False, True]


async def test_publishing_a_report_tells_the_client_and_the_account_manager(
    client: httpx.AsyncClient, world: World
) -> None:
    base = f"/projects/{world.project.id}/status-reports"
    draft = await ok(client, world.pm, "POST", base, {"rag": "green", "summary": "All good"})
    assert await inbox(client, world.contact) == []  # drafts are silent

    await ok(client, world.pm, "POST", f"{base}/{draft['id']}/publish")

    assert await types(client, world.contact) == ["status_report.published"]
    assert await types(client, world.am) == ["status_report.published"]
    assert await types(client, world.other_contact) == []


async def test_shared_milestones_tell_the_client(client: httpx.AsyncClient, world: World) -> None:
    base = f"/projects/{world.project.id}/milestones"
    shown = await ok(
        client,
        world.pm,
        "POST",
        base,
        {"name": "Go live", "due_date": day(10), "client_visible": True},
    )
    hidden = await ok(client, world.pm, "POST", base, {"name": "QA", "due_date": day(8)})
    await ok(
        client, world.pm, "PATCH", f"{base}/{hidden['id']}", {"version": 1, "due_date": day(9)}
    )
    moved = await ok(
        client, world.pm, "PATCH", f"{base}/{shown['id']}", {"version": 1, "due_date": day(12)}
    )
    await ok(
        client,
        world.pm,
        "PATCH",
        f"{base}/{shown['id']}",
        {"version": moved["version"], "done": True},
    )
    await ok(
        client, world.pm, "PATCH", f"{base}/{hidden['id']}", {"version": 2, "client_visible": True}
    )

    items = await inbox(client, world.contact)

    assert [(n["type"], n["params"]["name"]) for n in items] == [
        ("milestone.shared", "QA"),
        ("milestone.done", "Go live"),
        ("milestone.moved", "Go live"),
        ("milestone.shared", "Go live"),
    ]
    assert items[2]["params"]["previous_due_date"] == day(10)
    assert items[2]["params"]["due_date"] == day(12)
    assert await inbox(client, world.dev) == []


async def test_requirement_publish_and_answer(client: httpx.AsyncClient, world: World) -> None:
    base = f"/projects/{world.project.id}/requirements"
    created = await ok(
        client,
        world.pm,
        "POST",
        base,
        {
            "title": "Sign-in",
            "description": "Email sign-in",
            "acceptance_criteria": ["Works"],
            "owner_id": str(world.dev.id),
        },
    )
    await ok(client, world.pm, "POST", f"{base}/{created['id']}/publish", {"version": 1})

    assert await types(client, world.contact) == ["requirement.published"]

    await ok(
        client,
        world.contact,
        "POST",
        f"/client/projects/{world.project.id}/requirements/{created['id']}/response",
        {"version_number": 1, "decision": "accepted"},
    )

    for person in (world.pm, world.dev, world.am):  # the developer as the owner
        items = await inbox(client, person)
        assert [n["type"] for n in items] == ["requirement.answered"], person.email
        assert items[0]["params"]["decision"] == "accepted"


# --- settings -----------------------------------------------------------------------------------


async def test_settings_per_role_and_muting(client: httpx.AsyncClient, world: World) -> None:
    staff = await ok(client, world.pm, "GET", "/me/notification-settings")
    developer = await ok(client, world.dev, "GET", "/me/notification-settings")
    clients = await ok(client, world.contact, "GET", "/me/notification-settings")
    admin = await ok(client, world.admin, "GET", "/me/notification-settings")

    assert [s["key"] for s in staff["settings"]] == [
        "tasks_assigned",
        "tasks_reported",
        "mentions",
        "blocked_tasks",
        "change_requests",
        "requirements",
        "reports",
        "milestones",
        "projects",
    ]
    assert all(s["enabled"] for s in staff["settings"])
    assert [s["key"] for s in developer["settings"]] == [
        "tasks_assigned",
        "tasks_reported",
        "mentions",
        "requirements",
        "projects",
    ]
    assert [s["key"] for s in clients["settings"]] == [
        "change_requests",
        "requirements",
        "reports",
        "milestones",
    ]
    assert admin["settings"] == []

    muted = await ok(
        client,
        world.dev,
        "PUT",
        "/me/notification-settings",
        {"settings": {"tasks_assigned": False}},
    )
    assert {s["key"]: s["enabled"] for s in muted["settings"]}["tasks_assigned"] is False
    await new_task(client, world, assignee_id=str(world.dev.id))
    assert await inbox(client, world.dev) == []

    await ok(
        client,
        world.dev,
        "PUT",
        "/me/notification-settings",
        {"settings": {"tasks_assigned": True}},
    )
    await new_task(client, world, assignee_id=str(world.dev.id))
    assert await types(client, world.dev) == ["task.assigned"]

    wrong = await call(
        client, world.contact, "PUT", "/me/notification-settings", {"settings": {"mentions": False}}
    )
    assert wrong.status_code == 422
    assert wrong.json()["error"]["details"][0]["issue"] == "unknown_setting"


# --- reading ------------------------------------------------------------------------------------


async def test_read_one_read_all_and_pages(client: httpx.AsyncClient, world: World) -> None:
    for _ in range(3):
        await new_task(client, world, assignee_id=str(world.dev.id))
    items = await inbox(client, world.dev)

    await ok(client, world.dev, "POST", f"/me/notifications/{items[0]['id']}/read")
    await ok(client, world.dev, "POST", f"/me/notifications/{items[0]['id']}/read")  # idempotent
    assert await unread(client, world.dev) == 2
    other = await call(client, world.dev2, "POST", f"/me/notifications/{items[1]['id']}/read")
    assert other.status_code == 404

    first = await ok(client, world.dev, "GET", "/me/notifications?limit=2")
    second = await ok(
        client, world.dev, "GET", f"/me/notifications?limit=2&cursor={first['next_cursor']}"
    )
    assert [n["id"] for n in first["items"] + second["items"]] == [n["id"] for n in items]
    assert second["next_cursor"] is None
    only_unread = await ok(client, world.dev, "GET", "/me/notifications?unread=true")
    assert [n["id"] for n in only_unread["items"]] == [n["id"] for n in items[1:]]
    bad = await call(client, world.dev, "GET", "/me/notifications?cursor=nonsense")
    assert bad.status_code == 422

    marked = await ok(client, world.dev, "POST", "/me/notifications/read-all")
    assert marked == {"marked": 2}
    assert await unread(client, world.dev) == 0


async def test_a_removed_member_no_longer_sees_the_projects_notifications(
    client: httpx.AsyncClient, world: World
) -> None:
    await new_task(client, world, assignee_id=str(world.dev2.id))
    task = await new_task(client, world, assignee_id=str(world.dev.id))
    await ok(
        client,
        world.pm,
        "PUT",
        f"/tasks/{task['id']}/assignee",
        {"assignee_id": None, "version": 1},
    )
    assert await unread(client, world.dev) == 2

    await ok(client, world.pm, "DELETE", f"/projects/{world.project.id}/members/{world.dev.id}")

    assert await inbox(client, world.dev) == []
    assert await unread(client, world.dev) == 0


async def test_inactive_people_get_nothing(
    client: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    await session.execute(update(User).where(User.id == world.contact.id).values(is_active=False))
    await session.commit()

    base = f"/projects/{world.project.id}/status-reports"
    draft = await ok(client, world.pm, "POST", base, {"rag": "green", "summary": "x"})
    await ok(client, world.pm, "POST", f"{base}/{draft['id']}/publish")

    count = await session.scalar(
        select(func.count(Notification.id)).where(Notification.recipient_id == world.contact.id)
    )
    assert count == 0


async def test_cleanup_deletes_notifications_older_than_90_days(
    client: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    await new_task(client, world, assignee_id=str(world.dev.id))
    await new_task(client, world, assignee_id=str(world.dev.id))
    oldest = (await inbox(client, world.dev))[-1]
    await session.execute(
        update(Notification)
        .where(Notification.id == oldest["id"])
        .values(created_at=datetime.now(UTC) - timedelta(days=91))
    )
    await session.commit()

    deleted = await delete_old(session)

    assert deleted == 1
    assert len(await inbox(client, world.dev)) == 1


async def test_notifications_need_sign_in(client: httpx.AsyncClient) -> None:
    for path in (
        "/me/notifications",
        "/me/notifications/unread-count",
        "/me/notification-settings",
    ):
        assert (await client.get(API + path)).status_code == 401
