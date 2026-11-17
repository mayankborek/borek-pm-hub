"""GET /projects/{id}/labels: labels already used in a project, for the label picker (BB-03)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.projects.models import Project
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import build_app, client_for
from tests.test_tasks import as_user, join


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def labels_url(project: Project) -> str:
    return f"/api/v1/projects/{project.id}/labels"


async def test_lists_labels_most_used_first_with_counts(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, code="LBL")
    await make_task(session, project, pm.id, labels=["backend", "api"])
    await make_task(session, project, pm.id, labels=["backend"])
    await make_task(session, project, pm.id, labels=["Backend", "ui"])
    await make_task(session, project, pm.id, labels=[])

    response = await client.get(labels_url(project), headers=as_user(pm))

    assert response.status_code == 200
    # Most used first; ties by name ignoring case. Spellings stay apart, like the ?label= filter.
    assert response.json() == [
        {"name": "backend", "task_count": 2},
        {"name": "api", "task_count": 1},
        {"name": "Backend", "task_count": 1},
        {"name": "ui", "task_count": 1},
    ]


async def test_search_ignores_case_and_treats_wildcards_literally(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, code="LBS")
    await make_task(session, project, pm.id, labels=["Frontend", "front_end", "backend"])
    await make_task(session, project, pm.id, labels=["frontXend"])

    found = await client.get(labels_url(project), headers=as_user(pm), params={"q": " FRONT "})
    literal = await client.get(labels_url(project), headers=as_user(pm), params={"q": "t_e"})

    assert [x["name"] for x in found.json()] == ["front_end", "Frontend", "frontXend"]
    assert [x["name"] for x in literal.json()] == ["front_end"]  # "_" is not a wildcard


async def test_only_this_projects_active_tasks_count(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, code="LBA")
    other = await make_project(session, pm.id, code="LBO")
    await make_task(session, project, pm.id, labels=["kept"])
    await make_task(session, project, pm.id, labels=["kept", "gone"], archived_at=datetime.now(UTC))
    await make_task(session, other, pm.id, labels=["elsewhere"])

    response = await client.get(labels_url(project), headers=as_user(pm))

    assert response.json() == [{"name": "kept", "task_count": 1}]


async def test_limit_caps_the_list(client: httpx.AsyncClient, session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, code="LBM")
    await make_task(session, project, pm.id, labels=["a", "b", "c"])

    response = await client.get(labels_url(project), headers=as_user(pm), params={"limit": 2})
    too_big = await client.get(labels_url(project), headers=as_user(pm), params={"limit": 101})

    assert [x["name"] for x in response.json()] == ["a", "b"]
    assert too_big.status_code == 422


async def test_empty_project_returns_an_empty_list(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, code="LBE")

    response = await client.get(labels_url(project), headers=as_user(pm))

    assert response.status_code == 200
    assert response.json() == []


async def test_members_may_read_outsiders_get_404(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    outsider = await make_user(session)
    admin = await make_user(session, GlobalRole.ADMIN)
    project = await make_project(session, pm.id, code="LBP")
    await join(session, project, dev)
    await make_task(session, project, pm.id, labels=["secret"])

    as_dev = await client.get(labels_url(project), headers=as_user(dev))
    as_outsider = await client.get(labels_url(project), headers=as_user(outsider))
    as_admin = await client.get(labels_url(project), headers=as_user(admin))

    assert as_dev.status_code == 200
    assert as_outsider.status_code == 404  # does not even learn the project exists
    assert as_admin.status_code == 404  # administrators see no project data
    assert "secret" not in as_outsider.text + as_admin.text
