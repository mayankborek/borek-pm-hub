"""Per-project statuses: defaults, add, rename, reorder, delete with a move target."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.projects.models import Project, ProjectMember
from app.tasks.models import WorkflowStatus
from tests.conftest import make_project, make_task, make_user, status_by_name
from tests.test_auth import HEADER, build_app, client_for


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def as_user(user_id: uuid.UUID) -> dict[str, str]:
    return {HEADER: str(user_id)}


def url(project: Project, suffix: str = "") -> str:
    return f"/api/v1/projects/{project.id}/statuses{suffix}"


async def join(
    session: AsyncSession, project: Project, user_id: uuid.UUID, role: str = "developer"
) -> None:
    session.add(ProjectMember(project_id=project.id, user_id=user_id, project_role=role))
    await session.flush()


async def test_new_project_gets_the_default_statuses(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    created = await client.post(
        "/api/v1/projects", headers=as_user(pm.id), json={"code": "NEW", "name": "New"}
    )
    project_id = created.json()["id"]

    response = await client.get(f"/api/v1/projects/{project_id}/statuses", headers=as_user(pm.id))

    assert response.status_code == 200
    assert [(s["name"], s["category"], s["position"]) for s in response.json()] == [
        ("Backlog", "backlog", 0),
        ("To do", "todo", 1),
        ("In progress", "in_progress", 2),
        ("Code review", "in_progress", 3),
        ("Testing", "in_progress", 4),
        ("Blocked", "blocked", 5),
        ("Done", "done", 6),
    ]


async def test_members_can_list_but_outsiders_get_404(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    member, outsider = await make_user(session), await make_user(session)
    project = await make_project(session, pm.id)
    await join(session, project, member.id)

    assert (await client.get(url(project), headers=as_user(member.id))).status_code == 200
    assert (await client.get(url(project), headers=as_user(outsider.id))).status_code == 404
    assert (await client.get(url(project))).status_code == 401


async def test_pm_adds_renames_and_changes_category(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    headers = as_user(pm.id)

    added = await client.post(
        url(project), headers=headers, json={"name": " QA ", "category": "done"}
    )
    assert added.status_code == 201
    body = added.json()
    assert (body["name"], body["category"], body["position"], body["task_count"]) == (
        "QA",
        "done",
        7,
        0,
    )

    renamed = await client.patch(
        url(project, f"/{body['id']}"), headers=headers, json={"name": "QA done"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "QA done"
    assert renamed.json()["category"] == "done"  # several done statuses are allowed


async def test_project_lead_can_manage_statuses_but_plain_developer_cannot(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    lead, dev = await make_user(session), await make_user(session)
    project = await make_project(session, pm.id)
    await join(session, project, lead.id, "project_lead")
    await join(session, project, dev.id)
    payload = {"name": "Extra", "category": "todo"}

    assert (
        await client.post(url(project), headers=as_user(lead.id), json=payload)
    ).status_code == 201
    forbidden = await client.post(
        url(project), headers=as_user(dev.id), json={**payload, "name": "X"}
    )
    assert forbidden.status_code == 403


async def test_duplicate_and_invalid_status_input(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    headers = as_user(pm.id)

    duplicate = await client.post(
        url(project), headers=headers, json={"name": "To do", "category": "todo"}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_STATUS"

    for payload in [
        {"name": "  ", "category": "todo"},
        {"name": "X", "category": "weird"},
        {"name": "X"},
        {"name": "X", "category": "todo", "extra": 1},
    ]:
        response = await client.post(url(project), headers=headers, json=payload)
        assert response.status_code == 422, payload

    todo = await status_by_name(session, project.id, "To do")
    rename_clash = await client.patch(
        url(project, f"/{todo.id}"), headers=headers, json={"name": "Done"}
    )
    assert rename_clash.status_code == 409
    null_name = await client.patch(
        url(project, f"/{todo.id}"), headers=headers, json={"name": None}
    )
    assert null_name.status_code == 422


async def test_reorder_needs_every_status_exactly_once(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    headers = as_user(pm.id)
    current = (await client.get(url(project), headers=headers)).json()
    ids = [s["id"] for s in current]

    reordered = await client.put(
        url(project, "/order"), headers=headers, json={"status_ids": ids[::-1]}
    )
    assert reordered.status_code == 200
    assert [s["id"] for s in reordered.json()] == ids[::-1]
    assert [s["position"] for s in reordered.json()] == list(range(len(ids)))

    for bad in (ids[:-1], ids + ids[:1], [*ids[:-1], str(uuid.uuid4())]):
        response = await client.put(
            url(project, "/order"), headers=headers, json={"status_ids": bad}
        )
        assert response.status_code == 422


async def test_delete_unused_status(client: httpx.AsyncClient, session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    testing = await status_by_name(session, project.id, "Testing")

    response = await client.delete(url(project, f"/{testing.id}"), headers=as_user(pm.id))

    assert response.status_code == 204
    names = [s["name"] for s in (await client.get(url(project), headers=as_user(pm.id))).json()]
    assert "Testing" not in names


async def test_delete_status_in_use_needs_a_move_target_and_moves_tasks(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    headers = as_user(pm.id)
    review = await status_by_name(session, project.id, "Code review")
    done = await status_by_name(session, project.id, "Done")
    task = await make_task(session, project, pm.id, status="Code review")

    missing = await client.delete(url(project, f"/{review.id}"), headers=headers)
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "MOVE_TO_REQUIRED"
    same = await client.delete(
        url(project, f"/{review.id}"), headers=headers, params={"move_to": str(review.id)}
    )
    assert same.status_code == 422

    moved = await client.delete(
        url(project, f"/{review.id}"), headers=headers, params={"move_to": str(done.id)}
    )

    assert moved.status_code == 204
    await session.refresh(task)
    assert task.status_id == done.id
    assert task.completed_at is not None  # moving into a done status completes the task
    assert task.version == 2
    assert await session.get(WorkflowStatus, review.id) is None


async def test_moving_tasks_to_a_blocked_status_gives_them_a_reason(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    testing = await status_by_name(session, project.id, "Testing")
    blocked = await status_by_name(session, project.id, "Blocked")
    task = await make_task(session, project, pm.id, status="Testing")

    response = await client.delete(
        url(project, f"/{testing.id}"), headers=as_user(pm.id), params={"move_to": str(blocked.id)}
    )

    assert response.status_code == 204
    await session.refresh(task)
    assert task.blocked_reason and task.blocked_at is not None


async def test_last_done_status_cannot_be_deleted_or_recategorised(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    headers = as_user(pm.id)
    done = await status_by_name(session, project.id, "Done")

    delete = await client.delete(url(project, f"/{done.id}"), headers=headers)
    change = await client.patch(
        url(project, f"/{done.id}"), headers=headers, json={"category": "todo"}
    )
    assert delete.status_code == 409 and delete.json()["error"]["code"] == "LAST_DONE_STATUS"
    assert change.status_code == 409

    # With a second done status the first one can go.
    await client.post(url(project), headers=headers, json={"name": "Shipped", "category": "done"})
    assert (await client.delete(url(project, f"/{done.id}"), headers=headers)).status_code == 204


async def test_changing_category_updates_tasks_in_that_status(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    testing = await status_by_name(session, project.id, "Testing")
    task = await make_task(session, project, pm.id, status="Testing")

    done_now = await client.patch(
        url(project, f"/{testing.id}"), headers=as_user(pm.id), json={"category": "done"}
    )
    assert done_now.status_code == 200
    await session.refresh(task)
    assert task.completed_at is not None

    back = await client.patch(
        url(project, f"/{testing.id}"), headers=as_user(pm.id), json={"category": "in_progress"}
    )
    assert back.status_code == 200
    await session.refresh(task)
    assert task.completed_at is None


async def test_task_count_ignores_archived_tasks(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    await make_task(session, project, pm.id, status="Testing")
    from datetime import UTC, datetime

    await make_task(session, project, pm.id, status="Testing", archived_at=datetime.now(UTC))

    listing = (await client.get(url(project), headers=as_user(pm.id))).json()

    assert {s["name"]: s["task_count"] for s in listing}["Testing"] == 1


async def test_status_of_another_project_is_404_and_archived_project_is_409(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    from datetime import UTC, datetime

    pm = await make_user(session, GlobalRole.PM)
    first = await make_project(session, pm.id, code="ONE")
    second = await make_project(session, pm.id, code="TWO")
    foreign = await status_by_name(session, second.id, "Testing")
    headers = as_user(pm.id)

    assert (
        await client.patch(url(first, f"/{foreign.id}"), headers=headers, json={"name": "Z"})
    ).status_code == 404

    first.archived_at = datetime.now(UTC)
    await session.flush()
    archived = await client.post(
        url(first), headers=headers, json={"name": "Q", "category": "todo"}
    )
    assert archived.status_code == 409
    assert archived.json()["error"]["code"] == "PROJECT_ARCHIVED"
    assert (
        await session.scalar(select(WorkflowStatus.id).where(WorkflowStatus.name == "Q"))
    ) is None
