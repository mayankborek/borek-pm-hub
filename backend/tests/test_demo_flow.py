"""PT-18 demo script, end to end through the HTTP API (the Sprint Review scenario).

PM creates a project -> creates and assigns a task -> developer retrieves it -> developer updates
the status -> PM sees the update -> data is read back from the database -> permissions hold.
"""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from tests.conftest import make_user
from tests.test_auth import HEADER, build_app, client_for


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


async def test_sprint_review_demo_script(client: httpx.AsyncClient, session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    other_dev = await make_user(session)
    as_pm = {HEADER: str(pm.id)}
    as_dev = {HEADER: str(dev.id)}
    as_other = {HEADER: str(other_dev.id)}

    # The frontend identifies the signed-in user and their role.
    me = await client.get("/api/v1/auth/me", headers=as_dev)
    assert me.status_code == 200 and me.json()["role"] == "developer"

    # PM creates a project with the developer as a member.
    created = await client.post(
        "/api/v1/projects",
        headers=as_pm,
        json={
            "code": "DEMO",
            "name": "Demo project",
            "members": [{"user_id": str(dev.id), "project_role": "developer"}],
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    # PM creates and assigns a task.
    task = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=as_pm,
        json={"title": "Build login", "priority": "high", "assignee_id": str(dev.id)},
    )
    assert task.status_code == 201
    task_id, version = task.json()["id"], task.json()["version"]

    # Developer retrieves it in My Work; a developer outside the project sees nothing.
    mine = await client.get("/api/v1/me/tasks", headers=as_dev)
    assert [t["id"] for t in mine.json()["items"]] == [task_id]
    assert (await client.get("/api/v1/me/tasks", headers=as_other)).json()["items"] == []

    # Developer moves the task to an in-progress status.
    statuses = (await client.get(f"/api/v1/projects/{project_id}/statuses", headers=as_dev)).json()
    in_progress = next(s for s in statuses if s["category"] == "in_progress")
    updated = await client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=as_dev,
        json={"status_id": in_progress["id"], "version": version},
    )
    assert updated.status_code == 200
    assert updated.json()["status"]["id"] == in_progress["id"]

    # PM sees the update in the task, the board and the dashboard.
    seen = await client.get(f"/api/v1/tasks/{task_id}", headers=as_pm)
    assert seen.json()["status"]["category"] == "in_progress"
    board = await client.get(f"/api/v1/projects/{project_id}/tasks?view=board", headers=as_pm)
    column = next(c for c in board.json()["columns"] if c["status"]["id"] == in_progress["id"])
    assert [t["id"] for t in column["tasks"]] == [task_id]
    assert (await client.get("/api/v1/dashboard", headers=as_pm)).status_code == 200

    # Permissions: the developer cannot do PM-only things or touch other people's projects.
    denied = await client.post(
        "/api/v1/projects", headers=as_dev, json={"code": "NOPE", "name": "No"}
    )
    assert denied.status_code == 403
    assert (await client.get(f"/api/v1/tasks/{task_id}", headers=as_other)).status_code == 404
    assert (await client.get("/api/v1/dashboard", headers=as_dev)).status_code == 403
    assert (await client.get("/api/v1/dashboard/me", headers=as_dev)).status_code == 200
    assert (await client.get("/api/v1/me/tasks")).status_code == 401
