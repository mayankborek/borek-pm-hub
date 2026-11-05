# ruff: noqa: F401, F811  (the fixtures of test_task_import are imported by name)
"""Import under real-world conditions: other PMs, files re-saved by Excel, broken or hostile
files, two uploads at once, big files. Nothing here may end in a server error or a duplicate."""

import asyncio
import time
from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.common.enums import GlobalRole
from app.tasks.models import Task, TaskComment
from tests.conftest import make_project, make_user
from tests.test_auth import build_app, client_for
from tests.test_task_import import (
    FILE,
    JAYA,
    World,
    as_user,
    client,
    count,
    issue,
    jira_csv,
    named,
    post_import,
    tasks_by_external,
    world,
)


async def test_every_pm_can_import_and_the_tasks_record_who_did_it(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,
) -> None:
    """A second PM (not the project's creator, not a member) imports with the same result."""
    other_pm = named(await make_user(session, GlobalRole.PM), "Second PM")
    response = await post_import(client, world.project, other_pm, FILE, dry_run=False)
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 3
    tasks = await tasks_by_external(session)
    assert {task.created_by for task in tasks.values()} == {other_pm.id}
    again = await post_import(client, world.project, world.pm, FILE, dry_run=False)
    assert (again.json()["created"], again.json()["skipped_existing"]) == (0, 3)


async def test_a_file_saved_again_by_excel_still_imports(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,
) -> None:
    """Semicolons, Windows-1252, no BOM, German dates, other column order and letter case."""
    text = (
        "ISSUE KEY;summary;Priority;created;Due Date;STATUS;Assignee\r\n"
        '"PT-7";"Prüfung für Müller";"High";"12.10.2026 11:31";"20.10.2026";'
        '"in progress";"jana example"\r\n'
        '"PT-8";"Zweite Aufgabe";"";"13-Oct-26";"";"Done";""\r\n'
    )
    body = (
        await post_import(client, world.project, world.pm, text.encode("cp1252"), dry_run=False)
    ).json()
    assert (body["created"], body["failed"], body["warning_count"]) == (2, 0, 0), body
    tasks = await tasks_by_external(session)
    first = tasks["PT-7"]
    assert first.title == "Prüfung für Müller"
    assert first.priority == "high"
    assert first.due_date == date(2026, 10, 20)
    assert first.created_at == datetime(2026, 10, 12, 11, 31, tzinfo=UTC)
    assert first.assignee_id == world.jaya.id
    assert tasks["PT-8"].created_at == datetime(2026, 10, 13, tzinfo=UTC)


MANY_LABELS = (
    "Summary," + ",".join(["Labels"] * 100) + "\nA," + ",".join(f"l{n}" for n in range(100))
)

HOSTILE: dict[str, bytes] = {
    "header only": b"Summary\n",
    "bom only": b"\xef\xbb\xbf",
    "unterminated quote": b'Summary\n"abc',
    "ragged rows": b"Summary,Issue key,Priority\nA\nB,PT-2,High,extra,extra\n",
    "duplicate summary column": b"Summary,Summary\n,Second\nFirst,\n",
    "unicode": "Summary\n😀 émoji\n‮RTL​ zero\né\n".encode(),
    "sql and script": (
        b'Summary,Description\n"\'; DROP TABLE tasks;--",'
        b'"<script>alert(1)</script> ${jndi:ldap://x} {{7*7}}"\n'
    ),
    "formulas": b"Summary,Assignee\n=cmd|'/C calc'!A0,@SUM(1)\n+1,-1\n",
    "huge title": b"Summary\n" + b"t" * 10_000 + b"\n",
    "control characters": (
        b"Summary\nA" + bytes(range(1, 32)).replace(b"\n", b"").replace(b"\r", b"") + b"B\n"
    ),
    "invalid utf-8": b"Summary\n\xff\xfe\x81 broken\n",
    "old mac line endings": b"Summary,Issue key\rA,PT-1\rB,PT-2\r",
    "field over 1 MB": b"Summary\n" + b"x" * 1_100_000 + b"\n",
    "only commas": b",,,\n,,,\n",
    "odd header spacing": b"  summary  ;ISSUE KEY\nA;PT-1\n",
    "100 label columns": (MANY_LABELS + "\n").encode(),
    "everything wrong": (
        b"Summary,Priority,Due date,Original estimate,Created,Status\nA,??,99/99/99,-5,x,\x7f\n"
    ),
    "huge numbers": (
        b"Summary,Original estimate,Estimate,Estimate unit\nA,99999999999999999999999,1e9,hours\n"
    ),
}


@pytest.mark.parametrize("name", list(HOSTILE))
async def test_odd_files_never_cause_a_server_error(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,
    name: str,
) -> None:
    """Whatever is uploaded, the answer is 200 with honest numbers or 422 with a reason. After
    a real import the export works and imports again into another project."""
    response = await post_import(client, world.project, world.pm, HOSTILE[name], dry_run=False)
    assert response.status_code in (200, 422), (name, response.status_code, response.text[:300])
    if response.status_code == 422:
        assert response.json()["error"]["code"] == "IMPORT_BAD_FILE"
        assert await count(session, Task) == 0
        return
    body = response.json()
    assert body["created"] + body["skipped_existing"] + body["failed"] == body["total_rows"]
    assert await count(session, Task) == body["created"]

    exported = await client.get(
        f"/api/v1/projects/{world.project.id}/tasks/export", headers=as_user(world.pm)
    )
    assert exported.status_code == 200
    target = await make_project(session, world.pm.id, code="RT")
    back = await post_import(client, target, world.pm, exported.content, dry_run=False)
    assert back.status_code == 200, (name, back.text[:300])
    assert back.json()["created"] == body["created"]
    assert back.json()["failed"] == 0


async def test_importing_the_rest_of_a_partly_imported_file(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,
) -> None:
    rows = [issue(f"PT-{n}", f"Task {n}") for n in range(1, 11)]
    first = await post_import(client, world.project, world.pm, jira_csv(*rows[:4]), dry_run=False)
    assert first.json()["created"] == 4
    rest = await post_import(client, world.project, world.pm, jira_csv(*rows), dry_run=False)
    assert (rest.json()["created"], rest.json()["skipped_existing"]) == (6, 4)
    assert await count(session, Task) == 10
    keys = sorted(task.key for task in (await tasks_by_external(session)).values())
    assert keys == sorted(f"BFL-{n}" for n in range(1, 11))  # no gaps, no repeats


async def test_two_imports_at_the_same_moment_never_create_duplicates(
    session: AsyncSession,
    world: World,
    test_db_url: str,
) -> None:
    """Two PMs upload the same file together: nobody gets a duplicate; the loser is told to run
    it again (409) or finds the tasks already there."""
    await session.commit()
    engine = create_async_engine(test_db_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    pm, project = world.pm, world.project

    async def run() -> httpx.Response:
        async with maker() as own, client_for(build_app(own)) as http:
            return await post_import(http, project, pm, FILE, dry_run=False)

    try:
        answers = await asyncio.gather(run(), run())
    finally:
        await engine.dispose()
    assert all(a.status_code in (200, 409) for a in answers), [a.text[:200] for a in answers]
    assert sum(a.json()["created"] for a in answers if a.status_code == 200) == 3
    assert await count(session, Task) == 3
    keys = sorted(task.key for task in (await tasks_by_external(session)).values())
    assert keys == ["BFL-1", "BFL-2", "BFL-3"]


async def test_a_large_import_is_quick_and_complete(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,
) -> None:
    rows = [
        issue(
            f"PT-{n}",
            f"Task number {n}",
            Assignee="Jana Example",
            Labels=["A", "B"],
            Comment=[f"28/Oct/26 8:18 AM;{JAYA};comment {n}"],
            **{"Assignee Id": JAYA},
        )
        for n in range(1, 1001)
    ]
    started = time.perf_counter()
    response = await post_import(client, world.project, world.pm, jira_csv(*rows), dry_run=False)
    seconds = time.perf_counter() - started
    assert response.status_code == 200, response.text[:300]
    assert (response.json()["created"], response.json()["failed"]) == (1000, 0)
    assert await count(session, Task) == 1000
    assert await count(session, TaskComment) == 1000
    assert seconds < 30, seconds
