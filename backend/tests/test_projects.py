"""Project APIs (PT-15): CRUD, archive, search, membership and access rules."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.projects.models import Project, ProjectMember
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for

URL = "/api/v1/projects"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def as_user(user_id: uuid.UUID) -> dict[str, str]:
    return {HEADER: str(user_id)}


async def add_member(session: AsyncSession, project: Project, user_id: uuid.UUID) -> None:
    session.add(
        ProjectMember(project_id=project.id, user_id=user_id, granted_by=project.created_by)
    )
    await session.flush()


# --- create ---------------------------------------------------------------------------------


async def test_pm_creates_project_with_members(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)

    response = await client.post(
        URL,
        headers=as_user(pm.id),
        json={
            "code": " web-1 ",
            "name": "Website",
            "start_date": "2026-11-01",
            "target_end_date": "2026-12-01",
            "members": [{"user_id": str(dev.id), "project_role": "project_lead"}],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "WEB-1"  # trimmed and upper-cased
    assert body["status"] == "planned"
    assert body["version"] == 1
    assert body["created_by"] == str(pm.id)
    assert body["task_summary"]["total"] == 0
    assert [(m["user_id"], m["project_role"]) for m in body["members"]] == [
        (str(dev.id), "project_lead")
    ]
    assert response.headers["location"] == f"{URL}/{body['id']}"


async def test_developer_cannot_create_project(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    dev = await make_user(session)
    response = await client.post(URL, headers=as_user(dev.id), json={"code": "AB", "name": "X"})
    assert response.status_code == 403
    assert await session.scalar(select(Project.id)) is None


async def test_create_requires_sign_in(client: httpx.AsyncClient) -> None:
    response = await client.post(URL, json={"code": "AB", "name": "X"})
    assert response.status_code == 401


async def test_duplicate_code_is_rejected_case_insensitively(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    await make_project(session, pm.id, code="DUP")

    response = await client.post(URL, headers=as_user(pm.id), json={"code": "dup", "name": "X"})

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "DUPLICATE_CODE"
    assert error["details"][0]["field"] == "code"


async def test_invalid_input_is_rejected_without_saving(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    cases = [
        {"code": "AB", "name": "   "},  # blank name
        {"code": "A", "name": "X"},  # code too short
        {"code": "bad code!", "name": "X"},  # illegal characters
        {"code": "AB", "name": "X", "status": "nonsense"},
        {"code": "AB", "name": "X", "start_date": "2026-12-01", "target_end_date": "2026-11-01"},
        {"code": "AB", "name": "X", "unknown_field": 1},
    ]
    for payload in cases:
        response = await client.post(URL, headers=as_user(pm.id), json=payload)
        assert response.status_code == 422, payload
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert await session.scalar(select(Project.id)) is None


async def test_unknown_or_duplicate_member_rejects_whole_request(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    unknown = {"user_id": str(uuid.uuid4())}
    same = {"user_id": str(dev.id)}

    for members in ([unknown], [same, same]):
        response = await client.post(
            URL, headers=as_user(pm.id), json={"code": "AB", "name": "X", "members": members}
        )
        assert response.status_code == 422
    assert await session.scalar(select(Project.id)) is None


# --- read / list ----------------------------------------------------------------------------


async def test_developer_sees_only_member_projects(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    mine = await make_project(session, pm.id, code="MINE")
    other = await make_project(session, pm.id, code="OTHER")
    await add_member(session, mine, dev.id)

    listing = await client.get(URL, headers=as_user(dev.id))
    assert [p["code"] for p in listing.json()["items"]] == ["MINE"]
    assert listing.json()["total"] == 1

    assert (await client.get(f"{URL}/{mine.id}", headers=as_user(dev.id))).status_code == 200
    hidden = await client.get(f"{URL}/{other.id}", headers=as_user(dev.id))
    assert hidden.status_code == 404  # existence is not revealed


async def test_pm_sees_all_projects_with_search_status_and_paging(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    alpha = await make_project(session, pm.id, code="ALPHA")
    alpha.name = "Portal rebuild"
    alpha.status = "active"
    await make_project(session, pm.id, code="BETA")
    await make_project(session, pm.id, code="GAMMA")
    await session.flush()
    headers = as_user(pm.id)

    assert (await client.get(URL, headers=headers)).json()["total"] == 3
    by_name = await client.get(URL, headers=headers, params={"q": "rebuild"})
    assert [p["code"] for p in by_name.json()["items"]] == ["ALPHA"]
    by_code = await client.get(URL, headers=headers, params={"q": "bet"})
    assert [p["code"] for p in by_code.json()["items"]] == ["BETA"]
    wildcard = await client.get(URL, headers=headers, params={"q": "%"})
    assert wildcard.json()["total"] == 0  # '%' is a literal, not a wildcard
    active = await client.get(URL, headers=headers, params={"status": "active"})
    assert [p["code"] for p in active.json()["items"]] == ["ALPHA"]
    page = await client.get(URL, headers=headers, params={"page": 2, "page_size": 2})
    assert [p["code"] for p in page.json()["items"]] == ["GAMMA"]
    assert page.json()["total"] == 3
    assert (await client.get(URL, headers=headers, params={"page_size": 500})).status_code == 422


async def test_task_summary_has_every_count_the_frontend_shows(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, code="TSKS")
    today = datetime.now(UTC).date()
    yesterday, tomorrow = today - timedelta(days=1), today + timedelta(days=1)
    # (status name, due date, archived)
    tasks = [
        ("To do", yesterday, False),  # overdue
        ("In progress", tomorrow, False),
        ("Code review", tomorrow, False),  # also counts as in progress (same category)
        ("Blocked", yesterday, False),  # blocked and overdue
        ("Done", yesterday, False),  # done, so not overdue
        ("Done", None, False),
        ("To do", yesterday, True),  # archived, ignored
    ]
    for number, (status, due, archived) in enumerate(tasks, start=1):
        await make_task(
            session,
            project,
            pm.id,
            status=status,
            title=f"t{number}",
            due_date=due,
            blocked_reason="waiting" if status == "Blocked" else None,
            archived_at=datetime.now(UTC) if archived else None,
        )
    await session.flush()
    expected = {
        "total": 6,
        "completed": 2,
        "in_progress": 2,
        "blocked": 1,
        "overdue": 2,
        "completion_percent": 33,
    }

    listing = await client.get(URL, headers=as_user(pm.id))
    detail = await client.get(f"{URL}/{project.id}", headers=as_user(pm.id))

    assert listing.json()["items"][0]["task_summary"] == expected
    assert detail.json()["task_summary"] == expected


async def test_project_without_tasks_has_zero_summary(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)

    detail = await client.get(f"{URL}/{project.id}", headers=as_user(pm.id))

    assert detail.json()["task_summary"] == {
        "total": 0,
        "completed": 0,
        "in_progress": 0,
        "blocked": 0,
        "overdue": 0,
        "completion_percent": 0,
    }


async def test_unknown_project_is_404_and_bad_id_is_422(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    assert (await client.get(f"{URL}/{uuid.uuid4()}", headers=as_user(pm.id))).status_code == 404
    assert (await client.get(f"{URL}/not-a-uuid", headers=as_user(pm.id))).status_code == 422


# --- update ---------------------------------------------------------------------------------


async def test_pm_updates_project_and_version_increases(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, code="UPD")

    response = await client.patch(
        f"{URL}/{project.id}",
        headers=as_user(pm.id),
        json={"version": 1, "name": "Renamed", "status": "active", "start_date": "2026-11-02"},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["status"], body["start_date"]) == ("Renamed", "active", "2026-11-02")
    assert body["code"] == "UPD"
    assert body["version"] == 2


async def test_patch_can_clear_optional_fields(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    project.description = "old"
    await session.flush()

    response = await client.patch(
        f"{URL}/{project.id}",
        headers=as_user(pm.id),
        json={"version": project.version, "description": None},
    )

    assert response.status_code == 200
    assert response.json()["description"] is None
    assert response.json()["name"] == "Test project"  # untouched


async def test_code_cannot_be_changed(client: httpx.AsyncClient, session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, code="KEEP")

    response = await client.patch(
        f"{URL}/{project.id}", headers=as_user(pm.id), json={"version": 1, "code": "NEW"}
    )

    assert response.status_code == 422
    await session.refresh(project)
    assert project.code == "KEEP"


async def test_stale_version_gives_409(client: httpx.AsyncClient, session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    url, headers = f"{URL}/{project.id}", as_user(pm.id)

    assert (
        await client.patch(url, headers=headers, json={"version": 1, "name": "A"})
    ).status_code == 200
    stale = await client.patch(url, headers=headers, json={"version": 1, "name": "B"})

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


async def test_update_validates_dates_against_stored_values(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    from datetime import date

    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    project.start_date = date(2026, 11, 10)
    await session.flush()

    response = await client.patch(
        f"{URL}/{project.id}",
        headers=as_user(pm.id),
        json={"version": project.version, "target_end_date": "2026-11-01"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "target_end_date"


async def test_null_name_or_status_is_rejected(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    for payload in ({"name": None}, {"status": None}):
        response = await client.patch(
            f"{URL}/{project.id}", headers=as_user(pm.id), json={"version": 1, **payload}
        )
        assert response.status_code == 422


async def test_developer_cannot_update_or_archive(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    project = await make_project(session, pm.id)
    await add_member(session, project, dev.id)
    url, headers = f"{URL}/{project.id}", as_user(dev.id)

    assert (
        await client.patch(url, headers=headers, json={"version": 1, "name": "Z"})
    ).status_code == 403
    assert (await client.delete(url, headers=headers)).status_code == 403
    await session.refresh(project)
    assert project.name == "Test project"
    assert project.archived_at is None


async def test_non_member_developer_gets_404_on_write(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    project = await make_project(session, pm.id)
    url, headers = f"{URL}/{project.id}", as_user(dev.id)

    assert (await client.patch(url, headers=headers, json={"version": 1})).status_code == 404
    assert (await client.delete(url, headers=headers)).status_code == 404


# --- archive --------------------------------------------------------------------------------


async def test_archive_hides_project_but_keeps_data(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    project = await make_project(session, pm.id, code="OLD")
    await add_member(session, project, dev.id)
    url = f"{URL}/{project.id}"

    assert (await client.delete(url, headers=as_user(pm.id))).status_code == 204
    assert (await client.delete(url, headers=as_user(pm.id))).status_code == 204  # idempotent

    assert (await client.get(URL, headers=as_user(pm.id))).json()["total"] == 0
    with_archived = await client.get(URL, headers=as_user(pm.id), params={"include_archived": True})
    assert [p["code"] for p in with_archived.json()["items"]] == ["OLD"]
    assert with_archived.json()["items"][0]["archived_at"] is not None
    assert (await client.get(url, headers=as_user(pm.id))).status_code == 200
    # Developers never see it, even with the flag.
    dev_list = await client.get(URL, headers=as_user(dev.id), params={"include_archived": True})
    assert dev_list.json()["total"] == 0
    assert (await client.get(url, headers=as_user(dev.id))).status_code == 404

    row = await session.scalar(select(Project).where(Project.code == "OLD"))
    assert row is not None  # never physically deleted


async def test_archived_project_cannot_be_edited(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    await client.delete(f"{URL}/{project.id}", headers=as_user(pm.id))

    response = await client.patch(
        f"{URL}/{project.id}", headers=as_user(pm.id), json={"version": 1, "name": "Nope"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROJECT_ARCHIVED"


# --- members --------------------------------------------------------------------------------


async def test_member_lifecycle(client: httpx.AsyncClient, session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    project = await make_project(session, pm.id)
    base, headers = f"{URL}/{project.id}/members", as_user(pm.id)

    added = await client.post(base, headers=headers, json={"user_id": str(dev.id)})
    assert added.status_code == 201
    assert added.json()["project_role"] == "developer"

    again = await client.post(base, headers=headers, json={"user_id": str(dev.id)})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ALREADY_MEMBER"

    promoted = await client.patch(
        f"{base}/{dev.id}", headers=headers, json={"project_role": "project_lead"}
    )
    assert promoted.status_code == 200
    assert promoted.json()["project_role"] == "project_lead"

    listing = await client.get(base, headers=as_user(dev.id))  # members may see the team
    assert [m["user_id"] for m in listing.json()] == [str(dev.id)]

    assert (await client.delete(f"{base}/{dev.id}", headers=headers)).status_code == 204
    assert (await client.delete(f"{base}/{dev.id}", headers=headers)).status_code == 404
    assert (await client.get(base, headers=as_user(dev.id))).status_code == 404  # access is gone


async def test_unknown_user_cannot_be_added(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)

    response = await client.post(
        f"{URL}/{project.id}/members", headers=as_user(pm.id), json={"user_id": str(uuid.uuid4())}
    )

    assert response.status_code == 422


async def test_developer_cannot_manage_members(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    other = await make_user(session)
    project = await make_project(session, pm.id)
    await add_member(session, project, dev.id)
    base, headers = f"{URL}/{project.id}/members", as_user(dev.id)

    assert (
        await client.post(base, headers=headers, json={"user_id": str(other.id)})
    ).status_code == 403
    assert (
        await client.patch(
            f"{base}/{dev.id}", headers=headers, json={"project_role": "project_lead"}
        )
    ).status_code == 403
    assert (await client.delete(f"{base}/{dev.id}", headers=headers)).status_code == 403


async def test_removing_member_unassigns_their_tasks(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    project = await make_project(session, pm.id)
    await add_member(session, project, dev.id)
    task = await make_task(session, project, pm.id, assignee_id=dev.id)

    response = await client.delete(f"{URL}/{project.id}/members/{dev.id}", headers=as_user(pm.id))

    assert response.status_code == 204
    await session.refresh(task)
    assert task.assignee_id is None
    assert task.version == 2


# --- cancelled projects ---------------------------------------------------------------------


async def test_project_can_be_created_cancelled_and_reopened(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    headers = as_user(pm.id)

    created = await client.post(
        URL, headers=headers, json={"code": "CAN", "name": "Stopped", "status": "cancelled"}
    )
    assert created.status_code == 201 and created.json()["status"] == "cancelled"
    project_id = created.json()["id"]

    fetched = await client.get(f"{URL}/{project_id}", headers=headers)
    assert fetched.json()["status"] == "cancelled"
    listed = await client.get(URL, headers=headers, params={"status": "cancelled"})
    assert [p["code"] for p in listed.json()["items"]] == ["CAN"]

    reopened = await client.patch(
        f"{URL}/{project_id}", headers=headers, json={"version": 1, "status": "active"}
    )
    assert reopened.status_code == 200 and reopened.json()["status"] == "active"

    again = await client.patch(
        f"{URL}/{project_id}", headers=headers, json={"version": 2, "status": "cancelled"}
    )
    assert again.json()["status"] == "cancelled"


async def test_cancelled_project_keeps_its_tasks_inside_the_project(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, code="KEEP")
    await make_task(session, project, pm.id, title="Still here")
    project.status = "cancelled"
    await session.flush()

    response = await client.get(f"{URL}/{project.id}/tasks", headers=as_user(pm.id))

    assert [t["title"] for t in response.json()["items"]] == ["Still here"]
    detail = await client.get(f"{URL}/{project.id}", headers=as_user(pm.id))
    assert detail.json()["task_summary"]["total"] == 1
