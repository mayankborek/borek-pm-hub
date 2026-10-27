"""Permission-matrix gaps (PT-18): member reads, refused edits, cross-view data, auth."""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_task, status_by_name
from tests.test_auth import build_app, client_for
from tests.test_tasks import World, as_user, world  # noqa: F401  (world is a pytest fixture)


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


async def test_members_list_needs_membership(client: httpx.AsyncClient, world: World) -> None:  # noqa: F811
    url = f"/api/v1/projects/{world.project.id}/members"
    for user in (world.pm, world.dev, world.other_dev):
        response = await client.get(url, headers=as_user(user))
        assert response.status_code == 200
        assert {m["user_id"] for m in response.json()} >= {
            str(world.dev.id),
            str(world.other_dev.id),
        }
    assert (await client.get(url, headers=as_user(world.outsider))).status_code == 404
    assert (await client.get(url)).status_code == 401


async def test_refused_edit_on_a_teammates_task_changes_nothing(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,  # noqa: F811
) -> None:
    theirs = await make_task(session, world.project, world.pm.id, assignee_id=world.other_dev.id)
    review = await status_by_name(session, world.project.id, "Code review")
    pm = as_user(world.pm)
    history_before = (await client.get(f"/api/v1/tasks/{theirs.id}/activity", headers=pm)).json()

    denied = await client.patch(
        f"/api/v1/tasks/{theirs.id}",
        headers=as_user(world.dev),
        json={"version": 1, "status_id": str(review.id)},
    )
    assert denied.status_code == 403

    task = (await client.get(f"/api/v1/tasks/{theirs.id}", headers=pm)).json()
    assert task["version"] == 1 and "progress" not in task
    assert task["status"]["name"] == "To do"
    history_after = (await client.get(f"/api/v1/tasks/{theirs.id}/activity", headers=pm)).json()
    assert history_after["total"] == history_before["total"]


async def test_developer_status_change_shows_the_same_in_every_view(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,  # noqa: F811
) -> None:
    mine = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    await make_task(session, world.project, world.pm.id, assignee_id=world.other_dev.id)
    done = await status_by_name(session, world.project.id, "Done")
    pm, dev = as_user(world.pm), as_user(world.dev)
    base = f"/api/v1/projects/{world.project.id}/tasks"

    before = (await client.get("/api/v1/dashboard", headers=pm)).json()["summary"]
    assert before["total"] == 2 and before["completed"] == 0

    changed = await client.patch(
        f"/api/v1/tasks/{mine.id}",
        headers=dev,
        json={"version": 1, "status_id": str(done.id)},
    )
    assert changed.status_code == 200

    # PM: task detail, filtered list, board column, dashboard, history
    detail = (await client.get(f"/api/v1/tasks/{mine.id}", headers=pm)).json()
    assert detail["status"]["name"] == "Done"
    assert detail["version"] == 2 and detail["completed_at"] is not None

    listed = (await client.get(base, headers=pm, params={"category": "done"})).json()
    assert [t["id"] for t in listed["items"]] == [str(mine.id)]

    board = (await client.get(base, headers=pm, params={"view": "board"})).json()
    column = next(c for c in board["columns"] if c["status"]["name"] == "Done")
    assert column["total"] == 1 and column["tasks"][0]["id"] == str(mine.id)

    after = (await client.get("/api/v1/dashboard", headers=pm)).json()["summary"]
    assert after["total"] == 2 and after["completed"] == 1 and after["completion_percent"] == 50

    activity = (await client.get(f"/api/v1/tasks/{mine.id}/activity", headers=pm)).json()
    assert activity["items"][0]["actor"]["name"] == world.dev.name

    # Developer: My Work and own dashboard agree; the teammate sees the same task
    my_tasks = (await client.get("/api/v1/me/tasks", headers=dev)).json()
    assert [t["id"] for t in my_tasks["items"]] == [str(mine.id)]
    assert my_tasks["items"][0]["status"]["name"] == "Done"
    mine_dash = (await client.get("/api/v1/dashboard/me", headers=dev)).json()["summary"]
    assert mine_dash["total"] == 1 and mine_dash["completed"] == 1
    peer = await client.get(f"/api/v1/tasks/{mine.id}", headers=as_user(world.other_dev))
    assert peer.status_code == 200 and peer.json()["status"]["name"] == "Done"


async def test_anonymous_requests_are_refused_everywhere(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,  # noqa: F811
) -> None:
    task = await make_task(session, world.project, world.pm.id)
    pid, tid = world.project.id, task.id
    for path in (
        "/api/v1/auth/me",
        "/api/v1/projects",
        f"/api/v1/projects/{pid}",
        f"/api/v1/projects/{pid}/members",
        f"/api/v1/projects/{pid}/statuses",
        f"/api/v1/projects/{pid}/tasks",
        "/api/v1/tasks",
        "/api/v1/me/tasks",
        f"/api/v1/tasks/{tid}",
        f"/api/v1/tasks/{tid}/activity",
        f"/api/v1/tasks/{tid}/comments",
        f"/api/v1/tasks/{tid}/attachments",
        "/api/v1/users",
        "/api/v1/dashboard",
        "/api/v1/dashboard/me",
    ):
        response = await client.get(path)
        assert response.status_code == 401, path


async def test_deactivated_user_is_refused_everywhere(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,  # noqa: F811
) -> None:
    task = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    world.dev.is_active = False
    await session.flush()
    for path in ("/api/v1/auth/me", "/api/v1/me/tasks", f"/api/v1/tasks/{task.id}"):
        response = await client.get(path, headers=as_user(world.dev))
        assert response.status_code == 401, path


async def test_estimate_is_an_amount_and_unit_set_by_the_pm_and_read_by_everyone(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,  # noqa: F811
) -> None:
    pm, dev = as_user(world.pm), as_user(world.dev)
    created = await client.post(
        f"/api/v1/projects/{world.project.id}/tasks",
        headers=pm,
        json={
            "title": "Sized",
            "estimate_value": 90,
            "estimate_unit": "minutes",
            "assignee_id": str(world.dev.id),
        },
    )
    assert created.status_code == 201
    assert (created.json()["estimate_value"], created.json()["estimate_unit"]) == (90, "minutes")
    task_id, version = created.json()["id"], created.json()["version"]

    seen = (await client.get(f"/api/v1/tasks/{task_id}", headers=dev)).json()
    assert (seen["estimate_value"], seen["estimate_unit"]) == (90, "minutes")

    url = f"/api/v1/tasks/{task_id}"
    denied = await client.patch(
        url, headers=dev, json={"version": version, "estimate_value": 1, "estimate_unit": "hours"}
    )
    assert denied.status_code == 403

    for payload in (
        {"estimate_value": 0, "estimate_unit": "hours"},
        {"estimate_value": -3, "estimate_unit": "hours"},
        {"estimate_value": 2, "estimate_unit": "days"},
        {"estimate_value": None},  # clearing only one half
        {"estimate_unit": None},
    ):
        rejected = await client.patch(url, headers=pm, json={"version": version, **payload})
        assert rejected.status_code == 422, payload

    changed = await client.patch(
        url, headers=pm, json={"version": version, "estimate_value": 2, "estimate_unit": "weeks"}
    )
    assert changed.status_code == 200
    assert (changed.json()["estimate_value"], changed.json()["estimate_unit"]) == (2, "weeks")
    history = (await client.get(f"/api/v1/tasks/{task_id}/activity", headers=pm)).json()
    assert history["items"][0]["changes"]["estimate"] == ["90 minutes", "2 weeks"]

    # an amount alone is fine when the unit stays
    amount_only = await client.patch(
        url, headers=pm, json={"version": changed.json()["version"], "estimate_value": 3}
    )
    assert amount_only.status_code == 200 and amount_only.json()["estimate_unit"] == "weeks"

    cleared = await client.patch(
        url,
        headers=pm,
        json={
            "version": amount_only.json()["version"],
            "estimate_value": None,
            "estimate_unit": None,
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["estimate_value"] is None and cleared.json()["estimate_unit"] is None


async def test_estimate_needs_both_amount_and_unit_on_create(
    client: httpx.AsyncClient,
    world: World,  # noqa: F811
) -> None:
    for payload in ({"estimate_value": 5}, {"estimate_unit": "hours"}):
        response = await client.post(
            f"/api/v1/projects/{world.project.id}/tasks",
            headers=as_user(world.pm),
            json={"title": "x", **payload},
        )
        assert response.status_code == 422, payload
