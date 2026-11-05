"""Task export (S2-32): file format, formula protection, visibility, filters."""

import csv
import io
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole, StatusCategory, TaskPriority
from app.tasks import service, transfer
from app.tasks.schemas import StatusBrief, TaskOut, UserBrief
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import build_app, client_for
from tests.test_tasks import World, as_user, join

NOW = datetime(2026, 11, 5, 9, 30, 15, tzinfo=UTC)


def parse(content: bytes) -> list[list[str]]:
    """Read an export the way Excel would: UTF-8 with BOM, semicolon separated."""
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))


def out(**values: Any) -> TaskOut:
    """A TaskOut with sensible defaults, for tests of the file writer alone."""
    reporter = UserBrief(id=uuid.uuid4(), name="Rita Example", email="rina@test.example")
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "key": "BF-1",
        "external_key": None,
        "project_id": uuid.uuid4(),
        "project_name": "Borek Flow",
        "title": "A task",
        "description": None,
        "status": StatusBrief(id=uuid.uuid4(), name="To do", category=StatusCategory.TODO),
        "priority": TaskPriority.MEDIUM,
        "labels": [],
        "start_date": None,
        "due_date": None,
        "estimate_value": None,
        "estimate_unit": None,
        "assignee": None,
        "reporter": reporter,
        "blocked_reason": None,
        "blocked_at": None,
        "completed_at": None,
        "created_at": NOW,
        "updated_at": NOW,
        "archived_at": None,
        "version": 1,
    }
    fields.update(values)
    return TaskOut(**fields)


# --- the file ---------------------------------------------------------------------------------


def test_file_has_bom_header_and_one_row_per_task() -> None:
    raw = transfer.build_csv([out(), out(key="BF-2", title="Second")])
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = parse(raw)
    assert rows[0] == list(transfer.EXPORT_COLUMNS)
    assert [row[0] for row in rows[1:]] == ["BF-1", "BF-2"]


def test_all_fields_are_written() -> None:
    task = out(
        description="Line 1\nLine 2; with a separator",
        priority=TaskPriority.HIGHEST,
        labels=["Bug"],
        start_date=date(2026, 11, 1),
        due_date=date(2026, 11, 20),
        estimate_value=3,
        estimate_unit="hours",
        completed_at=NOW,
        assignee=UserBrief(id=uuid.uuid4(), name="Jana Example", email="jaya@test.example"),
    )
    row = dict(zip(transfer.EXPORT_COLUMNS, parse(transfer.build_csv([task]))[1], strict=False))
    assert row["Issue key"] == "BF-1"
    assert row["Project key"] == "BF"
    assert row["Project name"] == "Borek Flow"
    assert row["Description"] == "Line 1\nLine 2; with a separator"
    assert row["Status"] == "To do"
    assert row["Priority"] == "highest"
    assert row["Assignee"] == "Jana Example"
    assert row["Assignee email"] == "jaya@test.example"
    assert row["Labels"] == "Bug"
    assert row["Start date"] == "2026-11-01"
    assert row["Due date"] == "2026-11-20"
    assert row["Estimate"] == "3"
    assert row["Estimate unit"] == "hours"
    assert row["Created"] == "2026-11-05T09:30:15+00:00"
    assert row["Resolved"] == "2026-11-05T09:30:15+00:00"


def test_empty_values_stay_empty() -> None:
    row = parse(transfer.build_csv([out()]))[1]
    by_name = dict(zip(transfer.EXPORT_COLUMNS, row, strict=False))
    for column in ("Description", "Assignee", "Assignee email", "Labels", "Due date", "Estimate"):
        assert by_name[column] == ""


def test_umlauts_survive() -> None:
    rows = parse(transfer.build_csv([out(title="Prüfung für Müller", labels=["Größe"])]))
    assert rows[1][3] == "Prüfung für Müller"
    assert "Größe" in rows[1]


def test_one_labels_column_per_label_like_jira() -> None:
    rows = parse(transfer.build_csv([out(labels=["A", "B", "C"]), out(labels=["D"])]))
    assert rows[0].count("Labels") == 3
    first = rows[0].index("Labels")
    assert rows[1][first : first + 3] == ["A", "B", "C"]
    assert rows[2][first : first + 3] == ["D", "", ""]


def test_empty_export_still_has_the_header() -> None:
    rows = parse(transfer.build_csv([]))
    assert rows == [list(transfer.EXPORT_COLUMNS)]


# --- formula protection -----------------------------------------------------------------------


@pytest.mark.parametrize("start", ["=", "+", "-", "@", "\t", "\r"])
def test_cells_that_look_like_formulas_are_defused(start: str) -> None:
    title = f'{start}HYPERLINK("http://evil.example")'
    cell = parse(transfer.build_csv([out(title=title)]))[1][3]
    assert cell == "'" + title
    assert transfer.unprotect_cell(cell) == title  # the import gives the original text back


def test_normal_text_is_not_changed_and_a_plain_quote_stays() -> None:
    assert transfer.protect_cell("Fix login") == "Fix login"
    assert transfer.protect_cell("") == ""
    assert transfer.unprotect_cell("'quoted by the user") == "'quoted by the user"
    assert transfer.unprotect_cell("Fix login") == "Fix login"
    assert transfer.unprotect_cell("") == ""


def test_description_and_assignee_name_are_defused_too() -> None:
    task = out(
        description="=1+1",
        assignee=UserBrief(id=uuid.uuid4(), name="@SUM(A1)", email="x@test.example"),
    )
    row = dict(zip(transfer.EXPORT_COLUMNS, parse(transfer.build_csv([task]))[1], strict=False))
    assert row["Description"] == "'=1+1"
    assert row["Assignee"] == "'@SUM(A1)"


# --- the endpoints ----------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


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


def export_url(world: World) -> str:
    return f"/api/v1/projects/{world.project.id}/tasks/export"


async def test_pm_exports_a_project(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    first = await make_task(session, world.project, world.pm.id, title="First")
    await make_task(
        session,
        world.project,
        world.pm.id,
        title="Second",
        status="In progress",
        priority="high",
        assignee_id=world.dev.id,
        external_key="PT-27",
    )
    response = await client.get(export_url(world), headers=as_user(world.pm))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].startswith('attachment; filename="tasks-BFL-')
    assert response.headers["content-disposition"].endswith('.csv"')
    rows = parse(response.content)
    assert [row[0] for row in rows[1:]] == [first.key, "BFL-2"]  # oldest first
    second = dict(zip(rows[0], rows[2], strict=False))
    assert second["Status"] == "In progress"
    assert second["Priority"] == "high"
    assert second["Assignee"] == "Test User"


async def test_member_developer_can_export_own_project(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.project, world.pm.id)
    response = await client.get(export_url(world), headers=as_user(world.dev))
    assert response.status_code == 200
    assert len(parse(response.content)) == 2


async def test_outsider_gets_404_for_a_project_export(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.project, world.pm.id)
    response = await client.get(export_url(world), headers=as_user(world.outsider))
    assert response.status_code == 404


async def test_unknown_project_is_404(client: httpx.AsyncClient, world: World) -> None:
    url = f"/api/v1/projects/{uuid.uuid4()}/tasks/export"
    assert (await client.get(url, headers=as_user(world.pm))).status_code == 404


async def test_export_needs_a_login(client: httpx.AsyncClient, world: World) -> None:
    assert (await client.get(export_url(world))).status_code == 401
    assert (await client.get("/api/v1/tasks/export")).status_code == 401


async def test_project_export_applies_the_list_filters(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.project, world.pm.id, title="Urgent", priority="highest")
    await make_task(session, world.project, world.pm.id, title="Calm", priority="low")
    response = await client.get(
        export_url(world), params={"priority": "highest"}, headers=as_user(world.pm)
    )
    titles = [row[3] for row in parse(response.content)[1:]]
    assert titles == ["Urgent"]


async def test_category_filter_and_search(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.project, world.pm.id, title="Open one")
    await make_task(session, world.project, world.pm.id, title="Finished one", status="Done")
    done = await client.get(
        export_url(world), params={"category": "done"}, headers=as_user(world.pm)
    )
    assert [row[3] for row in parse(done.content)[1:]] == ["Finished one"]
    found = await client.get(export_url(world), params={"q": "open"}, headers=as_user(world.pm))
    assert [row[3] for row in parse(found.content)[1:]] == ["Open one"]


async def test_archived_tasks_are_left_out_unless_the_pm_asks(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.project, world.pm.id, title="Live")
    await make_task(
        session, world.project, world.pm.id, title="Gone", archived_at=datetime.now(UTC)
    )
    default = await client.get(export_url(world), headers=as_user(world.pm))
    assert [row[3] for row in parse(default.content)[1:]] == ["Live"]
    with_archived = await client.get(
        export_url(world), params={"include_archived": "true"}, headers=as_user(world.pm)
    )
    assert sorted(row[3] for row in parse(with_archived.content)[1:]) == ["Gone", "Live"]
    # developers cannot ask for archived tasks
    dev = await client.get(
        export_url(world), params={"include_archived": "true"}, headers=as_user(world.dev)
    )
    assert [row[3] for row in parse(dev.content)[1:]] == ["Live"]


async def test_cross_project_export_shows_each_role_only_its_own(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    other = await make_project(session, world.pm.id, code="OTH")
    await make_task(session, world.project, world.pm.id, title="In BFL")
    await make_task(session, other, world.pm.id, title="In OTH")

    pm = await client.get("/api/v1/tasks/export", headers=as_user(world.pm))
    assert sorted(row[3] for row in parse(pm.content)[1:]) == ["In BFL", "In OTH"]
    assert pm.headers["content-disposition"].startswith('attachment; filename="tasks-all-')

    dev = await client.get("/api/v1/tasks/export", headers=as_user(world.dev))
    assert [row[3] for row in parse(dev.content)[1:]] == ["In BFL"]  # never the foreign project

    nobody = await client.get("/api/v1/tasks/export", headers=as_user(world.outsider))
    assert len(parse(nobody.content)) == 1  # header only


async def test_developer_cannot_reach_a_foreign_project_through_the_project_filter(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    other = await make_project(session, world.pm.id, code="OTH")
    await make_task(session, other, world.pm.id, title="Secret")
    response = await client.get(
        "/api/v1/tasks/export", params={"project_id": str(other.id)}, headers=as_user(world.dev)
    )
    assert response.status_code == 200
    assert len(parse(response.content)) == 1


async def test_cross_project_export_skips_archived_and_cancelled_projects(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    cancelled = await make_project(session, world.pm.id, code="CNC")
    cancelled.status = "cancelled"
    archived = await make_project(session, world.pm.id, code="ARC")
    archived.archived_at = datetime.now(UTC)
    await make_task(session, world.project, world.pm.id, title="Live")
    await make_task(session, cancelled, world.pm.id, title="Cancelled")
    await make_task(session, archived, world.pm.id, title="Archived")
    response = await client.get("/api/v1/tasks/export", headers=as_user(world.pm))
    assert [row[3] for row in parse(response.content)[1:]] == ["Live"]


async def test_formula_in_a_title_is_defused_in_the_download(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.project, world.pm.id, title="=cmd|' /C calc'!A0")
    response = await client.get(export_url(world), headers=as_user(world.pm))
    assert parse(response.content)[1][3] == "'=cmd|' /C calc'!A0"


async def test_export_over_the_limit_is_refused_not_cut_off(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "MAX_EXPORT_ROWS", 2)
    for number in range(3):
        await make_task(session, world.project, world.pm.id, title=f"T{number}")
    response = await client.get(export_url(world), headers=as_user(world.pm))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EXPORT_TOO_LARGE"
    narrowed = await client.get(
        export_url(world), params={"priority": "high"}, headers=as_user(world.pm)
    )
    assert narrowed.status_code == 200  # nothing matches the narrower filter: header only


# --- external key -----------------------------------------------------------------------------


async def test_external_key_is_in_the_task_and_found_by_search(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    imported = await make_task(session, world.project, world.pm.id, external_key="PT-27")
    await make_task(session, world.project, world.pm.id)
    detail = await client.get(f"/api/v1/tasks/{imported.id}", headers=as_user(world.pm))
    assert detail.json()["external_key"] == "PT-27"
    found = await client.get(
        f"/api/v1/projects/{world.project.id}/tasks",
        params={"q": "PT-27"},
        headers=as_user(world.pm),
    )
    assert [item["id"] for item in found.json()["items"]] == [str(imported.id)]
    own = await client.get(
        f"/api/v1/tasks/{(await make_task(session, world.project, world.pm.id)).id}",
        headers=as_user(world.pm),
    )
    assert own.json()["external_key"] is None


async def test_the_same_external_key_cannot_exist_twice_in_a_project(
    session: AsyncSession, world: World
) -> None:
    await make_task(session, world.project, world.pm.id, external_key="PT-1")
    with pytest.raises(IntegrityError):
        await make_task(session, world.project, world.pm.id, external_key="PT-1")
    await session.rollback()


async def test_many_tasks_without_external_key_are_fine(
    session: AsyncSession, world: World
) -> None:
    for _ in range(3):
        await make_task(session, world.project, world.pm.id)  # all NULL: no clash
    assert world.project.task_counter == 3
