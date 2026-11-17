"""PDF task list export (BB-05): readable, same tasks as CSV/XLSX for the same scope."""

import re
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import EstimateUnit, GlobalRole, TaskPriority
from app.tasks import pdf_export
from app.tasks.schemas import UserBrief
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import build_app, client_for
from tests.test_task_export import out, parse
from tests.test_tasks import as_user

AT = datetime(2026, 11, 17, 14, 5, tzinfo=UTC)


def cells(content: bytes) -> list[str]:
    """Text drawn on the pages (uncompressed PDF: one `(text) Tj` per piece)."""
    found = re.findall(rb"\(((?:[^()\\]|\\.)*)\) Tj", content)
    return [re.sub(r"\\(.)", r"\1", m.decode("cp1252")) for m in found]  # undo \( \) \\


def build(tasks: list[Any], **kw: Any) -> bytes:
    kw.setdefault("title", "Borek Flow (BF)")
    kw.setdefault("filters", [])
    return pdf_export.build_pdf(tasks, exported_at=AT, compress=False, **kw)


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


@pytest.fixture
def readable_pdfs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the tests read the text of PDFs made through the API."""
    real = pdf_export.build_pdf

    def uncompressed(*args: Any, **kwargs: Any) -> bytes:
        return real(*args, **{**kwargs, "compress": False})

    monkeypatch.setattr(pdf_export, "build_pdf", uncompressed)


# --- the file ---------------------------------------------------------------------------------


def test_pdf_has_heading_columns_and_one_row_per_task() -> None:
    dana = UserBrief(id=out().reporter.id, name="Dana Dev", email="d@test.example")
    tasks = [
        out(
            title="Build login",
            priority=TaskPriority.HIGHEST,
            assignee=dana,
            labels=["ui", "api"],
            start_date=date(2026, 11, 2),
            due_date=date(2026, 11, 20),
            estimate_value=1,
            estimate_unit=EstimateUnit.WEEKS,
        ),
        out(key="BF-2", title="Second", estimate_value=3, estimate_unit=EstimateUnit.HOURS),
    ]

    content = build(tasks, filters=["priority high"])

    assert content.startswith(b"%PDF")
    text = cells(content)
    assert "Tasks: Borek Flow (BF)" in text
    assert "Exported 17.11.2026 14:05 UTC  |  2 tasks" in text
    assert any("Filters: priority high" in t for t in text)
    assert text[text.index("Key") : text.index("Key") + 9] == list(pdf_export.COLUMNS)
    row = text.index("BF-1")
    assert text[row : row + 9] == [
        "BF-1", "Build login", "To do", "Highest", "Dana Dev", "ui, api",
        "02.11.2026", "20.11.2026", "1 week",
    ]  # fmt: skip
    assert "3 hours" in text


def test_long_lists_repeat_the_headings_on_every_page() -> None:
    tasks = [out(key=f"BF-{n}", title="A fairly long task title " * 3) for n in range(1, 121)]

    content = build(tasks)

    pages = int(re.findall(rb"/Count (\d+)", content)[0])
    text = cells(content)
    assert pages >= 3
    assert text.count("Key") == pages
    assert [t for t in text if re.fullmatch(r"BF-\d+", t)] == [f"BF-{n}" for n in range(1, 121)]
    assert f"Page {pages} of {pages}" in text


def test_characters_outside_the_pdf_fonts_become_question_marks() -> None:
    content = build([out(title="Grüße für 5 € 🙂 “ok” Ωmega")], title="Café ☕")

    text = cells(content)
    assert "Grüße für 5 € ? “ok” ?mega" in text  # euro sign and curly quotes are kept
    assert "Tasks: Café ?" in text


def test_an_empty_scope_still_gives_a_pdf() -> None:
    text = cells(build([]))

    assert "No tasks match these filters." in text
    assert "Exported 17.11.2026 14:05 UTC  |  0 tasks" in text
    assert any("Filters: none" in t for t in text)


# --- through the API --------------------------------------------------------------------------


@pytest.mark.usefixtures("readable_pdfs")
async def test_pdf_lists_the_same_tasks_as_the_csv_for_the_same_filters(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    pm.name = "Pia PM"
    project = await make_project(session, pm.id, code="PDF")
    for n, priority in enumerate(["high", "low", "high", "medium", "high"], start=1):
        await make_task(session, project, pm.id, title=f"Task {n}", priority=priority)
    await make_task(session, project, pm.id, title="Old", priority="high", archived_at=AT)
    url = f"/api/v1/projects/{project.id}/tasks/export"
    params = {"priority": "high", "assignee_id": str(pm.id)}

    unfiltered = await client.get(url, headers=as_user(pm), params={"format": "pdf"})
    pdf = await client.get(url, headers=as_user(pm), params={**params, "format": "pdf"})
    csv_file = await client.get(url, headers=as_user(pm), params=params)
    high_pdf = await client.get(
        url, headers=as_user(pm), params={"priority": "high", "format": "pdf"}
    )
    high_csv = await client.get(url, headers=as_user(pm), params={"priority": "high"})

    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].endswith('.pdf"')

    def pdf_keys(response: httpx.Response) -> list[str]:
        return [t for t in cells(response.content) if re.fullmatch(r"PDF-\d+", t)]

    def csv_keys(response: httpx.Response) -> list[str]:
        return [row[0] for row in parse(response.content)[1:]]

    assert pdf_keys(high_pdf) == csv_keys(high_csv) == ["PDF-1", "PDF-3", "PDF-5"]
    assert pdf_keys(pdf) == csv_keys(csv_file) == []  # nobody is assigned
    assert pdf_keys(unfiltered) == ["PDF-1", "PDF-2", "PDF-3", "PDF-4", "PDF-5"]  # not archived
    heading = cells(pdf.content)
    assert "Tasks: Test project (PDF)" in heading
    assert any("Filters: priority high; assignee Pia PM" in t for t in heading)


@pytest.mark.usefixtures("readable_pdfs")
async def test_cross_project_pdf_follows_visibility_and_names_nothing_hidden(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    other_pm = await make_user(session, GlobalRole.PM)
    mine = await make_project(session, pm.id, code="MYP")
    hidden = await make_project(session, other_pm.id, code="HID")
    hidden.name = "Secret client work"
    await make_task(session, mine, pm.id, title="Mine")
    await make_task(session, hidden, other_pm.id, title="Not mine")

    everything = await client.get(
        "/api/v1/tasks/export", headers=as_user(pm), params={"format": "pdf"}
    )
    probe = await client.get(
        "/api/v1/tasks/export",
        headers=as_user(pm),
        params={"format": "pdf", "project_id": str(hidden.id)},
    )

    text = cells(everything.content)
    assert "Tasks: my projects" in text
    assert "Mine" in text and "Not mine" not in text
    probed = cells(probe.content)
    assert "Tasks: selected project" in probed
    assert not any("Secret" in t for t in probed)


async def test_outsiders_get_404_for_the_pdf_too(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    outsider = await make_user(session)
    project = await make_project(session, pm.id, code="PDO")

    response = await client.get(
        f"/api/v1/projects/{project.id}/tasks/export",
        headers=as_user(outsider),
        params={"format": "pdf"},
    )

    assert response.status_code == 404
