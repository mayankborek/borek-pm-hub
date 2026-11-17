"""XLSX export and import of tasks (BB-05): same table as the CSV, safe both ways."""

import io
import zipfile
from collections.abc import AsyncIterator
from datetime import date, datetime

import httpx
import pytest
import pytest_asyncio
from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import EstimateUnit, GlobalRole, TaskPriority
from app.tasks import csv_import, transfer
from app.tasks.csv_import import ImportFileError, parse_file
from app.tasks.models import Task
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import build_app, client_for
from tests.test_task_export import out
from tests.test_tasks import as_user

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def sheet_rows(content: bytes) -> list[list[object]]:
    workbook = load_workbook(io.BytesIO(content))
    assert workbook.sheetnames == ["Tasks"]
    return [list(row) for row in workbook["Tasks"].iter_rows(values_only=True)]


def workbook_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# --- the file ---------------------------------------------------------------------------------


def test_xlsx_holds_the_same_table_as_the_csv() -> None:
    tasks = [
        out(title='Grüße, "Zitat"; Semikolon', labels=["ui", "api"], due_date=date(2026, 12, 1)),
        out(key="BF-2", title="Second", description="Line 1\nLine 2"),
    ]

    rows = sheet_rows(transfer.build_xlsx(tasks))

    expected = transfer.build_table(tasks)
    assert [[cell or "" for cell in row] for row in rows] == expected


def test_formulas_are_written_as_text_never_as_formulas() -> None:
    content = transfer.build_xlsx([out(title='=HYPERLINK("http://evil")', description="+1")])

    workbook = load_workbook(io.BytesIO(content))  # not data_only: a formula would show as one
    title, description = workbook["Tasks"]["D2"], workbook["Tasks"]["E2"]
    assert title.data_type == "s" and title.value == '\'=HYPERLINK("http://evil")'
    assert description.data_type == "s" and description.value == "'+1"


def test_our_xlsx_export_imports_back_unchanged() -> None:
    task = out(
        title="=1+1 is two",
        description="Details\nmore",
        priority=TaskPriority.HIGH,
        labels=["backend", "Grüße"],
        start_date=date(2026, 11, 1),
        due_date=date(2026, 11, 20),
        estimate_value=3,
        estimate_unit=EstimateUnit.HOURS,
    )

    parsed = parse_file(transfer.build_xlsx([task]), "tasks.xlsx")

    assert parsed.failures == []
    row = parsed.rows[0]
    assert (row.external_key, row.title, row.description) == (
        "BF-1",
        "=1+1 is two",
        "Details\nmore",
    )
    assert row.priority == TaskPriority.HIGH
    assert row.labels == ["backend", "Grüße"]
    assert (row.start_date, row.due_date) == (date(2026, 11, 1), date(2026, 11, 20))
    assert (row.estimate_value, row.estimate_unit) == (3, EstimateUnit.HOURS)


def test_a_workbook_made_in_excel_with_real_dates_and_numbers_is_read() -> None:
    data = workbook_bytes(
        [
            [None],  # a blank first row before the header is skipped
            ["Summary", "Due date", "Estimate", "Estimate unit", "Labels", "Labels"],
            ["From Excel", datetime(2026, 12, 24), 2.0, "hours", "x", None],
            [None, None, None, None, None, None],  # blank rows are dropped
            ["Second", date(2027, 1, 5), 1, "weeks", None, "y"],
        ]
    )

    parsed = parse_file(data, "made-in-excel.xlsx")

    assert parsed.total_rows == 2
    first, second = parsed.rows
    assert (first.title, first.due_date, first.estimate_value) == (
        "From Excel",
        date(2026, 12, 24),
        2,
    )
    assert first.labels == ["x"]
    assert (second.due_date, second.estimate_unit, second.labels) == (
        date(2027, 1, 5),
        EstimateUnit.WEEKS,
        ["y"],
    )


def test_a_formula_cell_is_never_run_only_its_saved_value_counts() -> None:
    # openpyxl saves formulas without a computed value, like a file that was never opened.
    data = workbook_bytes([["Summary", "Description"], ["=1+1", "kept"], ["Real", "=2+2"]])

    parsed = parse_file(data, "f.xlsx")

    assert [row.title for row in parsed.rows] == ["Real"]
    assert parsed.rows[0].description is None
    assert len(parsed.failures) == 1  # the row whose Summary was only a formula


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"not a zip at all", "Excel"),
        (b"Summary\nA\n", "Excel"),
        (b"", "empty"),
    ],
)
def test_broken_workbooks_are_refused(data: bytes, message: str) -> None:
    with pytest.raises(ImportFileError, match=message):
        parse_file(data, "x.xlsx")


def test_a_zip_that_is_not_a_workbook_is_refused() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "hi")

    with pytest.raises(ImportFileError, match="Excel"):
        parse_file(buffer.getvalue(), "x.xlsx")


def test_a_workbook_that_unpacks_too_large_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(csv_import, "MAX_XLSX_UNPACKED", 1_000)

    with pytest.raises(ImportFileError, match="too large"):
        parse_file(workbook_bytes([["Summary"], ["A"]]), "x.xlsx")


def test_too_many_rows_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(csv_import, "MAX_IMPORT_ROWS", 2)

    with pytest.raises(ImportFileError, match="more than 2"):
        parse_file(workbook_bytes([["Summary"], ["A"], ["B"], ["C"]]), "x.xlsx")


def test_xml_attacks_are_blocked_by_defusedxml() -> None:
    from openpyxl.xml import DEFUSEDXML

    assert DEFUSEDXML  # defusedxml is installed, so openpyxl parses uploads with it


# --- through the API --------------------------------------------------------------------------


async def test_export_as_xlsx_and_import_into_another_project(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    source = await make_project(session, pm.id, code="XLS")
    target = await make_project(session, pm.id, code="XLT")
    await make_task(session, source, pm.id, title="=cmd|' /C calc'!A0", labels=["ops"])
    await make_task(session, source, pm.id, title="Normal", priority="high")

    exported = await client.get(
        f"/api/v1/projects/{source.id}/tasks/export",
        headers=as_user(pm),
        params={"format": "xlsx"},
    )

    assert exported.status_code == 200
    assert exported.headers["content-type"] == XLSX
    assert exported.headers["content-disposition"].endswith('.xlsx"')
    imported = await client.post(
        f"/api/v1/projects/{target.id}/tasks/import",
        params={"dry_run": "false"},
        headers=as_user(pm),
        files={"file": ("tasks.xlsx", exported.content, XLSX)},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["created"] == 2
    titles = set(await session.scalars(select(Task.title).where(Task.project_id == target.id)))
    assert titles == {"=cmd|' /C calc'!A0", "Normal"}  # the protecting ' is gone again


async def test_csv_stays_the_default_and_other_formats_are_rejected(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, code="XLD")
    url = f"/api/v1/projects/{project.id}/tasks/export"

    default = await client.get(url, headers=as_user(pm))
    across = await client.get(
        "/api/v1/tasks/export", headers=as_user(pm), params={"format": "xlsx"}
    )
    bad = await client.get(url, headers=as_user(pm), params={"format": "docx"})

    assert default.headers["content-type"].startswith("text/csv")
    assert default.headers["content-disposition"].endswith('.csv"')
    assert across.headers["content-type"] == XLSX
    assert bad.status_code == 422
