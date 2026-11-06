"""Task import (S2-31): reading the file, matching, saving, permissions, re-import.

The sample files are built here with Jira's real column names and invented data. No real
client content is kept in the repository.
"""

import csv
import io
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import EstimateUnit, GlobalRole, TaskPriority
from app.projects.models import Project, ProjectMember
from app.tasks import csv_import, importer, router, transfer
from app.tasks.csv_import import ImportFileError, parse_file
from app.tasks.models import Task, TaskActivity, TaskAttachment, TaskComment, WorkflowStatus
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for
from tests.test_task_export import out, parse

# The 65 columns of the real Jira export (04.11.2026), repeated names included.
JIRA_HEADER = [
    "Summary", "Issue key", "Issue id", "Issue Type", "Status", "Project key", "Project name",
    "Project type", "Project lead", "Project lead id", "Project description", "Priority",
    "Resolution", "Assignee", "Assignee Id", "Reporter", "Reporter Id", "Creator", "Creator Id",
    "Created", "Updated", "Last Viewed", "Resolved", "Due date", "Votes", "Labels", "Labels",
    "Description", "Environment", "Watchers", "Watchers", "Watchers Id", "Watchers Id",
    "Original estimate", "Remaining Estimate", "Time Spent", "Work Ratio",
    "Σ Original Estimate", "Σ Remaining Estimate", "Σ Time Spent",
    "Security Level", "Inward issue link (Problem/Incident)",
    "Outward issue link (Problem/Incident)", "Attachment", "Attachment",
    "Custom field (Budget)", "Custom field (Budget)", "Custom field (Budget)",
    "Custom field (Category)", "Custom field (Development)", "Custom field (Issue color)",
    "Custom field (Rank)", "Custom field (Start date)", "Custom field (Story point estimate)",
    "Custom field (Team)", "Custom field (Vulnerability)", "Comment", "Comment", "Comment",
    "Comment", "Parent", "Parent key", "Parent summary", "Status category",
    "Status category changed",
]  # fmt: skip

RINA = "712020:aaaaaaaa-0000-0000-0000-000000000001"
JAYA = "712020:bbbbbbbb-0000-0000-0000-000000000002"


def jira_csv(*rows: dict[str, Any], separator: str = ",") -> bytes:
    """A Jira-shaped export. A row maps column names to text (or to a list for repeated
    columns such as Labels and Comment)."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=separator, lineterminator="\r\n")
    writer.writerow(JIRA_HEADER)
    for row in rows:
        seen: dict[str, int] = {}
        cells = []
        for name in JIRA_HEADER:
            value = row.get(name, "")
            if isinstance(value, list):
                position = seen.get(name, 0)
                seen[name] = position + 1
                value = value[position] if position < len(value) else ""
            cells.append(value)
        writer.writerow(cells)
    return buffer.getvalue().encode("utf-8")


def issue(key: str, summary: str = "A task", **values: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "Summary": summary,
        "Issue key": key,
        "Issue Type": "Task",
        "Status": "To Do",
        "Status category": "To Do",
        "Project key": "PT",
        "Priority": "Medium",
        "Created": "12/Oct/26 11:31 AM",
    }
    base.update(values)
    return base


def one(data: bytes) -> csv_import.ImportRow:
    parsed = parse_file(data, "jira.csv")
    assert len(parsed.rows) == 1, parsed.failures
    return parsed.rows[0]


# --- reading the file -------------------------------------------------------------------------


def test_utf8_with_bom_and_windows_1252_are_both_read() -> None:
    assert one("﻿Summary\nMüller\n".encode()).title == "Müller"
    assert one("Summary\nMüller\n".encode("cp1252")).title == "Müller"


@pytest.mark.parametrize(
    "data",
    [b"", b"  \n ", b"PK\x03\x04binary", b"%PDF-1.7 ...", b"Summary\x00\nA\n"],
)
def test_files_that_are_not_csv_text_are_refused(data: bytes) -> None:
    with pytest.raises(ImportFileError):
        parse_file(data, "x.csv")


def test_a_file_without_summary_column_is_refused_with_a_hint() -> None:
    with pytest.raises(ImportFileError, match="Summary"):
        parse_file(b"Titel,Status\nA,B\n", "x.csv")


def test_only_csv_files_are_accepted() -> None:
    with pytest.raises(ImportFileError, match="csv"):
        parse_file(b"Summary\nA\n", "tasks.xlsx")
    assert parse_file(b"Summary\nA\n", "TASKS.CSV").total_rows == 1


@pytest.mark.parametrize("separator", [",", ";", "\t"])
def test_separator_is_detected(separator: str) -> None:
    text = separator.join(["Summary", "Issue key", "Priority"]) + "\n"
    text += separator.join(["Fix login", "PT-1", "High"]) + "\n"
    row = one(text.encode())
    assert (row.title, row.external_key, row.priority) == ("Fix login", "PT-1", TaskPriority.HIGH)


def test_row_limit_and_blank_rows() -> None:
    assert parse_file(("Summary\n" + "x\n" * 5000).encode(), "x.csv").total_rows == 5000
    with pytest.raises(ImportFileError, match="5000"):
        parse_file(("Summary\n" + "x\n" * 5001).encode(), "x.csv")
    parsed = parse_file(b"Summary\nA\n\n  \nB\n", "x.csv")
    assert [row.row for row in parsed.rows] == [2, 5]  # spreadsheet row numbers
    assert parsed.total_rows == 2


def test_line_breaks_inside_quotes_and_long_text_are_kept() -> None:
    text = 'Summary,Description\nA,"line 1\r\nline 2, with comma"\nB,' + "x" * 200_000 + "\n"
    parsed = parse_file(text.encode(), "x.csv")
    assert parsed.rows[0].description == "line 1\nline 2, with comma"
    assert parsed.rows[1].row == 3  # records are counted, not lines
    assert parsed.rows[1].description is not None
    assert len(parsed.rows[1].description) <= 20_000  # cut to the limit
    assert any(w.field == "Description" for w in parsed.warnings)


def test_columns_with_the_same_name_are_all_read() -> None:
    row = one(jira_csv(issue("PT-1", Labels=["Frontend", "Sprint01"])))
    assert row.labels == ["Frontend", "Sprint01"]


def test_ignored_columns_and_projects_are_reported() -> None:
    parsed = parse_file(jira_csv(issue("PT-1"), issue("ABC-2", **{"Project key": "ABC"})), "j.csv")
    assert "Votes" in parsed.ignored_columns
    assert "Summary" not in parsed.ignored_columns
    assert "Labels" not in parsed.ignored_columns
    assert len(parsed.ignored_columns) == len(set(parsed.ignored_columns))
    assert parsed.projects == ["PT", "ABC"]


# --- values -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12/Oct/26 11:31 AM", datetime(2026, 10, 12, 11, 31, tzinfo=UTC)),
        ("12/Oct/26 12:00 AM", datetime(2026, 10, 12, 0, 0, tzinfo=UTC)),
        ("12/Oct/26 12:15 PM", datetime(2026, 10, 12, 12, 15, tzinfo=UTC)),
        ("1/Jan/2027 5:05 PM", datetime(2027, 1, 1, 17, 5, tzinfo=UTC)),
        ("28/oct/26", datetime(2026, 10, 28, tzinfo=UTC)),
        ("2026-11-05", datetime(2026, 11, 5, tzinfo=UTC)),
        ("2026-11-05T09:30:15+01:00", datetime(2026, 11, 5, 8, 30, 15, tzinfo=UTC)),
        ("2026-11-05T09:30:15Z", datetime(2026, 11, 5, 9, 30, 15, tzinfo=UTC)),
        ("", None),
        ("soon", None),
        ("32/Oct/26", None),
        ("12/Foo/26", None),
        ("12/Oct/26 13:00 PM", None),
    ],
)
def test_dates(raw: str, expected: datetime | None) -> None:
    result = csv_import.parse_datetime(raw)
    assert result == (expected.astimezone(UTC) if expected else None)


@pytest.mark.parametrize(
    ("seconds", "expected", "warns"),
    [
        (3600, (1, EstimateUnit.HOURS), False),
        (7200, (2, EstimateUnit.HOURS), False),
        (5400, (90, EstimateUnit.MINUTES), False),  # 1.5 hours stays exact
        (61, (2, EstimateUnit.MINUTES), False),  # rounded up to a whole minute
        (576_000, (160, EstimateUnit.HOURS), False),  # the cap
        (579_600, (5, EstimateUnit.WEEKS), True),  # 161 hours: weeks, rounded up
        (1_728_000, (12, EstimateUnit.WEEKS), True),  # 480 hours = 12 weeks of 40 hours
        (1_731_600, None, True),  # 481 hours: above everything
        (288_060, (3, EstimateUnit.WEEKS), True),  # 4801 minutes, not whole hours
        (0, None, False),
    ],
)
def test_estimate_conversion(
    seconds: int, expected: tuple[int, EstimateUnit] | None, warns: bool
) -> None:
    result, warning = csv_import.estimate_from_seconds(seconds)
    assert result == expected
    assert bool(warning) is warns


def test_estimate_columns() -> None:
    jira = one(jira_csv(issue("PT-1", **{"Original estimate": "7200"})))
    assert (jira.estimate_value, jira.estimate_unit) == (2, EstimateUnit.HOURS)
    own = one(b"Summary,Estimate,Estimate unit\nA,3,Hours\n")
    assert (own.estimate_value, own.estimate_unit) == (3, EstimateUnit.HOURS)
    for bad in (b"A,0,hours", b"A,999,hours", b"A,3,days", b"A,x,hours", b"A,3,"):
        parsed = parse_file(b"Summary,Estimate,Estimate unit\n" + bad + b"\n", "x.csv")
        assert parsed.rows[0].estimate_value is None, bad
        assert [w.field for w in parsed.warnings] == ["Estimate"], bad
    unreadable = parse_file(jira_csv(issue("PT-1", **{"Original estimate": "2h"})), "j.csv")
    assert unreadable.rows[0].estimate_value is None and unreadable.warnings


def test_bad_dates_are_dropped_with_a_warning() -> None:
    parsed = parse_file(
        jira_csv(
            issue("PT-1", **{"Due date": "not a date"}),
            issue("PT-2", **{"Due date": "01/Jan/1999", "Custom field (Start date)": "x"}),
            issue(
                "PT-3",
                **{"Due date": "01/Nov/26", "Custom field (Start date)": "05/Nov/26"},
            ),
            issue("PT-4", Created="garbage"),
        ),
        "j.csv",
    )
    by_key = {r.external_key: r for r in parsed.rows}
    assert by_key["PT-1"].due_date is None
    assert by_key["PT-2"].due_date is None and by_key["PT-2"].start_date is None
    assert by_key["PT-3"].due_date is None and by_key["PT-3"].start_date == date(2026, 11, 5)
    assert by_key["PT-4"].created_at is None
    fields = sorted((w.external_key or "", w.field or "") for w in parsed.warnings)
    assert fields == [
        ("PT-1", "Due date"),
        ("PT-2", "Due date"),
        ("PT-2", "Start date"),
        ("PT-3", "Due date"),
        ("PT-4", "Created"),
    ]


def test_valid_dates_are_read_from_jira_and_iso() -> None:
    row = one(
        jira_csv(
            issue(
                "PT-1",
                **{
                    "Due date": "23/Oct/26 12:00 AM",
                    "Custom field (Start date)": "20/Oct/26",
                    "Resolved": "28/Oct/26 4:00 PM",
                },
            )
        )
    )
    assert (row.start_date, row.due_date) == (date(2026, 10, 20), date(2026, 10, 23))
    assert row.resolved_at == datetime(2026, 10, 28, 16, 0, tzinfo=UTC)
    assert row.created_at == datetime(2026, 10, 12, 11, 31, tzinfo=UTC)
    own = one(b"Summary,Start date,Due date\nA,2026-11-01,2026-11-20\n")
    assert (own.start_date, own.due_date) == (date(2026, 11, 1), date(2026, 11, 20))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Highest", TaskPriority.HIGHEST),
        ("blocker", TaskPriority.HIGHEST),
        ("Critical", TaskPriority.HIGHEST),
        ("High", TaskPriority.HIGH),
        ("Major", TaskPriority.HIGH),
        ("Medium", TaskPriority.MEDIUM),
        ("Low", TaskPriority.LOW),
        ("Minor", TaskPriority.LOW),
        ("Lowest", TaskPriority.LOWEST),
        ("Trivial", TaskPriority.LOWEST),
        ("highest", TaskPriority.HIGHEST),  # our own export
        ("", TaskPriority.MEDIUM),
    ],
)
def test_priorities(raw: str, expected: TaskPriority) -> None:
    parsed = parse_file(jira_csv(issue("PT-1", Priority=raw)), "j.csv")
    assert parsed.rows[0].priority is expected
    assert not parsed.warnings


def test_unknown_priority_becomes_medium_with_a_warning() -> None:
    parsed = parse_file(jira_csv(issue("PT-1", Priority="Urgent!!")), "j.csv")
    assert parsed.rows[0].priority is TaskPriority.MEDIUM
    assert [w.field for w in parsed.warnings] == ["Priority"]


def test_labels_issue_type_and_limits() -> None:
    task = one(jira_csv(issue("PT-1", **{"Issue Type": "Task", "Labels": ["A"]})))
    assert task.labels == ["A"]  # "Task" would be on everything: left out
    bug = one(jira_csv(issue("PT-1", **{"Issue Type": "Bug", "Labels": ["A", "a"]})))
    assert bug.labels == ["A", "Bug"]  # duplicates ignoring case are dropped
    long = parse_file(b"Summary,Labels\nA," + b"x" * 40 + b"\n", "x.csv")
    assert long.rows[0].labels == ["x" * 30]
    assert [w.field for w in long.warnings] == ["Labels"]
    many = parse_file(
        (
            "Summary," + ",".join(["Labels"] * 12) + "\nA," + ",".join(f"l{i}" for i in range(12))
        ).encode(),
        "x.csv",
    )
    assert len(many.rows[0].labels) == 10
    assert [w.field for w in many.warnings] == ["Labels"]


def test_title_rules() -> None:
    parsed = parse_file(b'Summary,Issue key\n,PT-1\n   ,PT-2\n"a\x01b\nc",PT-3\n', "x.csv")
    assert [(f.row, f.external_key, f.field) for f in parsed.failures] == [
        (2, "PT-1", "Summary"),
        (3, "PT-2", "Summary"),
    ]
    assert parsed.rows[0].title == "ab c"  # control character removed, line break -> space
    long = one(("Summary\n" + "t" * 400 + "\n").encode())
    assert len(long.title) == 300


def test_too_long_issue_key_fails_the_row() -> None:
    parsed = parse_file(("Summary,Issue key\nA," + "K" * 51 + "\n").encode(), "x.csv")
    assert [f.field for f in parsed.failures] == ["Issue key"]
    assert not parsed.rows


def test_description_gets_reporter_and_parent_footer_and_mentions_are_named() -> None:
    parsed = parse_file(
        jira_csv(
            issue(
                "PT-5",
                Description=f"Ask [~accountid:{JAYA}] and [~accountid:712020:nobody]",
                Reporter="Rita Example",
                **{
                    "Reporter Id": RINA,
                    "Assignee": "Jana Example",
                    "Assignee Id": JAYA,
                    "Parent key": "PT-1",
                    "Parent summary": "Frontend",
                },
            )
        ),
        "j.csv",
    )
    assert parsed.rows[0].description == (
        "Ask @Jana Example and @unknown user\n\n---\n"
        "Reporter in Jira: Rita Example\nJira parent: PT-1 Frontend"
    )


def test_a_task_without_text_has_no_description() -> None:
    assert one(b"Summary\nA\n").description is None


def test_comments() -> None:
    parsed = parse_file(
        jira_csv(
            issue(
                "PT-1",
                **{"Assignee": "Rita Example", "Assignee Id": RINA},
                Comment=[
                    f"28/Oct/26 8:18 AM;{RINA};Hello; world [~accountid:{RINA}]",
                    "16/Oct/26 11:59 AM;712020:stranger;Who?",
                    "no date at all",
                    f"28/Oct/26 8:19 AM;{RINA};   ",
                ],
            )
        ),
        "j.csv",
    )
    first, second, third = parsed.rows[0].comments
    assert (first.author, first.body) == ("Rita Example", "Hello; world @Rita Example")
    assert first.when == datetime(2026, 10, 28, 8, 18, tzinfo=UTC)
    assert second.author == "unknown user"
    assert (third.author, third.when, third.body) == ("unknown user", None, "no date at all")


def test_attachments_keep_only_web_links() -> None:
    url = "https://team.atlassian.net/rest/api/3/attachment/content/10001"
    parsed = parse_file(
        jira_csv(
            issue(
                "PT-1",
                Attachment=[
                    f"27/Oct/26 5:05 PM;abc;image (2).png;{url}",
                    "27/Oct/26 5:05 PM;abc;evil.html;javascript:alert(1)",
                ],
            ),
            issue("PT-2", Attachment=["only;three;parts"]),
        ),
        "j.csv",
    )
    assert [(a.name, a.url) for a in parsed.rows[0].attachments] == [("image (2).png", url)]
    assert not parsed.rows[1].attachments
    assert [w.field for w in parsed.warnings] == ["Attachment", "Attachment"]


def test_assignee_can_be_an_email() -> None:
    row = one(jira_csv(issue("PT-1", Assignee="Jana@Test.Example")))
    assert (row.assignee, row.assignee_email) == (None, "jana@test.example")
    own = one(b"Summary,Assignee,Assignee email\nA,Jana Example,JAYA@test.example\n")
    assert (own.assignee, own.assignee_email) == ("Jana Example", "jaya@test.example")


def test_export_file_can_be_read_back() -> None:
    """The export is valid import input and the formula guard is undone."""
    task = out(
        key="BF-7",
        title="=SUM(A1)",
        description="Line 1\nLine 2",
        labels=["Bug", "Epic"],
        priority=TaskPriority.LOW,
        start_date=date(2026, 11, 1),
        due_date=date(2026, 11, 20),
        estimate_value=3,
        estimate_unit="hours",
    )
    row = one(transfer.build_csv([task]))
    assert row.title == "=SUM(A1)"
    assert row.external_key == "BF-7"
    assert row.project_key == "BF"
    assert row.description == "Line 1\nLine 2"
    assert row.labels == ["Bug", "Epic"]
    assert row.priority is TaskPriority.LOW
    assert (row.start_date, row.due_date) == (date(2026, 11, 1), date(2026, 11, 20))
    assert (row.estimate_value, row.estimate_unit) == (3, EstimateUnit.HOURS)
    assert row.status == "To do"
    assert row.created_at == datetime(2026, 11, 5, 9, 30, 15, tzinfo=UTC)


# --- matching: users and statuses -------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("Aida.Example", "Aida Example"),
        ("aida_example", "Aida Example"),
        ("  AIDA   EXAMPLE ", "Aida Example"),
    ],
)
def test_names_match_ignoring_case_dots_and_underscores(typed: str, stored: str) -> None:
    assert importer.normalize_name(typed) == importer.normalize_name(stored)


# --- the endpoint -----------------------------------------------------------------------------


class World:
    pm: User
    rina: User  # global PM, not yet a member
    jaya: User  # developer, member
    aida: User  # developer, not a member
    outsider: User
    project: Project


def named(user: User, name: str) -> User:
    user.name = name
    return user


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.pm = named(await make_user(session, GlobalRole.PM), "Mayank Somwani")
    w.rina = named(await make_user(session, GlobalRole.PM), "Rita Example")
    w.jaya = named(await make_user(session, email="jaya@test.example"), "Jana Example")
    w.aida = named(await make_user(session), "Aida Example")
    w.outsider = named(await make_user(session), "Olga Outsider")
    w.project = await make_project(session, w.pm.id, code="BFL")
    session.add(ProjectMember(project_id=w.project.id, user_id=w.jaya.id, project_role="developer"))
    await session.flush()
    return w


def as_user(user: User) -> dict[str, str]:
    return {HEADER: str(user.id)}


async def post_import(
    client: httpx.AsyncClient,
    project: Project,
    user: User,
    data: bytes,
    *,
    dry_run: bool | None = None,
    name: str = "jira.csv",
) -> httpx.Response:
    params = {} if dry_run is None else {"dry_run": str(dry_run).lower()}
    return await client.post(
        f"/api/v1/projects/{project.id}/tasks/import",
        params=params,
        files={"file": (name, data, "text/csv")},
        headers=as_user(user),
    )


async def count(session: AsyncSession, model: Any) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def tasks_by_external(session: AsyncSession) -> dict[str, Task]:
    rows = (await session.scalars(select(Task).where(Task.external_key.is_not(None)))).all()
    return {task.external_key or "": task for task in rows}


FILE = jira_csv(
    issue("PT-12", "Epic: Frontend", **{"Issue Type": "Epic", "Priority": "High"}),
    issue(
        "PT-27",
        "Build the board",
        Status="Testing/PM Review",
        Assignee="Jana Example",
        **{
            "Assignee Id": JAYA,
            "Status category": "In Progress",
            "Priority": "Highest",
            "Issue Type": "Bug",
            "Parent key": "PT-12",
            "Parent summary": "Epic: Frontend",
            "Due date": "14/Oct/20 12:00 AM",  # long past, so "overdue" does not depend on today
            "Original estimate": "7200",
            "Created": "13/Oct/26 9:00 AM",
        },
        Labels=["Frontend", "Sprint01"],
        Description=f"See [~accountid:{JAYA}]",
        Comment=[f"28/Oct/26 8:18 AM;{JAYA};Looks good; ship it"],
        Attachment=["27/Oct/26 5:05 PM;x;shot.png;https://team.atlassian.net/a/1"],
    ),
    issue("PT-5", "Fix login", Assignee="Rita Example", **{"Assignee Id": RINA}),
)


async def test_dry_run_is_the_default_and_writes_nothing(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await session.commit()
    default = await post_import(client, world.project, world.pm, FILE)
    explicit = await post_import(client, world.project, world.pm, FILE, dry_run=True)
    assert default.status_code == explicit.status_code == 200
    assert default.json() == explicit.json()
    body = default.json()
    assert body["dry_run"] is True
    assert (body["total_rows"], body["created"], body["failed"]) == (3, 3, 0)
    assert body["skipped_existing"] == 0
    assert body["unknown_statuses"] == {"Testing/PM Review": "Testing"}
    assert sorted(body["members_added"]) == ["Rita Example"]
    assert body["ignored_columns"] and "Votes" in body["ignored_columns"]
    for model in (Task, TaskComment, TaskAttachment, TaskActivity):
        assert await count(session, model) == 0
    await session.refresh(world.project)
    assert world.project.task_counter == 0
    members = await session.scalars(
        select(ProjectMember.user_id).where(ProjectMember.project_id == world.project.id)
    )
    assert set(members) == {world.jaya.id, world.pm.id}  # the PM leads the project


async def test_real_import_creates_tasks_in_jira_order(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    response = await post_import(client, world.project, world.pm, FILE, dry_run=False)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 3 and body["failed"] == 0 and body["dry_run"] is False

    tasks = await tasks_by_external(session)
    # numbers follow Jira's order (PT-5, PT-12, PT-27), not the order in the file
    assert {k: t.key for k, t in tasks.items()} == {
        "PT-5": "BFL-1",
        "PT-12": "BFL-2",
        "PT-27": "BFL-3",
    }
    await session.refresh(world.project)
    assert world.project.task_counter == 3

    task = tasks["PT-27"]
    assert task.title == "Build the board"
    assert task.priority == "highest"
    assert task.assignee_id == world.jaya.id
    assert task.created_by == world.pm.id  # the person importing
    assert task.labels == ["Frontend", "Sprint01", "Bug"]
    assert task.due_date == date(2020, 10, 14)
    assert (task.estimate_value, task.estimate_unit) == (2, "hours")
    assert task.created_at == datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    assert task.description == "See @Jana Example\n\n---\nJira parent: PT-12 Epic: Frontend"
    status = await session.get(WorkflowStatus, task.status_id)
    assert status is not None and status.name == "Testing"
    assert tasks["PT-12"].labels == ["Epic"]

    comment = (
        await session.scalars(select(TaskComment).where(TaskComment.task_id == task.id))
    ).one()
    assert comment.author_id == world.pm.id
    assert comment.body == "Comment by Jana Example on 28.10.2026 08:18:\nLooks good; ship it"
    assert comment.created_at == datetime(2026, 10, 28, 8, 18, tzinfo=UTC)
    link = (
        await session.scalars(select(TaskAttachment).where(TaskAttachment.task_id == task.id))
    ).one()
    assert (link.kind, link.name, link.url) == (
        "link",
        "shot.png",
        "https://team.atlassian.net/a/1",
    )
    assert link.uploaded_by == world.pm.id
    history = (
        await session.scalars(select(TaskActivity).where(TaskActivity.task_id == task.id))
    ).all()
    assert [(h.action, h.changes) for h in history] == [
        ("imported", {"external_key": [None, "PT-27"]})
    ]


async def test_assignees_join_the_project_pms_as_leads(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await post_import(client, world.project, world.pm, FILE, dry_run=False)
    rows = (
        await session.scalars(
            select(ProjectMember).where(ProjectMember.project_id == world.project.id)
        )
    ).all()
    by_user = {row.user_id: row for row in rows}
    assert set(by_user) == {world.jaya.id, world.rina.id, world.pm.id}  # Jana was already in
    assert by_user[world.rina.id].project_role == "project_lead"  # a global PM
    assert by_user[world.rina.id].source == "task_assignment"
    assert by_user[world.rina.id].granted_by == world.pm.id
    assert by_user[world.jaya.id].project_role == "developer"  # unchanged

    await post_import(
        client,
        world.project,
        world.pm,
        jira_csv(issue("PT-99", Assignee="Aida.Example")),
        dry_run=False,
    )
    added = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == world.project.id, ProjectMember.user_id == world.aida.id
        )
    )
    assert added is not None and added.project_role == "developer"


async def test_importing_twice_creates_nothing_the_second_time(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await post_import(client, world.project, world.pm, FILE, dry_run=False)
    again = await post_import(client, world.project, world.pm, FILE, dry_run=False)
    body = again.json()
    assert (body["created"], body["skipped_existing"], body["failed"]) == (0, 3, 0)
    assert await count(session, Task) == 3
    await session.refresh(world.project)
    assert world.project.task_counter == 3  # no numbers burnt
    preview = await post_import(client, world.project, world.pm, FILE)
    assert (preview.json()["created"], preview.json()["skipped_existing"]) == (0, 3)


async def test_numbers_continue_after_existing_tasks(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.project, world.pm.id)
    await make_task(session, world.project, world.pm.id)
    await post_import(
        client, world.project, world.pm, jira_csv(issue("PT-3"), issue("PT-1")), dry_run=False
    )
    tasks = await tasks_by_external(session)
    assert (tasks["PT-1"].key, tasks["PT-3"].key) == ("BFL-3", "BFL-4")
    new = await client.post(
        f"/api/v1/projects/{world.project.id}/tasks",
        json={"title": "Next"},
        headers=as_user(world.pm),
    )
    assert new.json()["key"] == "BFL-5"


async def test_a_key_twice_in_the_file_is_imported_once(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    data = jira_csv(issue("PT-1", "First"), issue("PT-1", "Second"))
    body = (await post_import(client, world.project, world.pm, data, dry_run=False)).json()
    assert (body["created"], body["skipped_existing"]) == (1, 1)
    assert [w["message"] for w in body["warnings"]] == ["The key is in the file twice."]
    assert (await tasks_by_external(session))["PT-1"].title == "First"


async def test_bad_rows_do_not_block_the_good_ones(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    data = jira_csv(issue("PT-1", "Good"), issue("PT-2", ""), issue("PT-3", "Also good"))
    body = (await post_import(client, world.project, world.pm, data, dry_run=False)).json()
    assert (body["total_rows"], body["created"], body["failed"]) == (3, 2, 1)
    assert body["failures"] == [
        {"row": 3, "external_key": "PT-2", "field": "Summary", "message": "Title is required."}
    ]
    assert sorted(await tasks_by_external(session)) == ["PT-1", "PT-3"]


async def test_rows_that_fail_the_task_rules_are_reported(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    # A title that is nothing but control characters is empty once cleaned: a failed row.
    data = jira_csv(issue("PT-1", "\x01\x02"), issue("PT-2", "Fine"))
    body = (await post_import(client, world.project, world.pm, data, dry_run=False)).json()
    assert (body["created"], body["failed"]) == (1, 1)
    assert body["failures"][0]["field"] == "Summary"


async def test_status_matching(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    data = jira_csv(
        issue("PT-1", Status="To Do"),  # same name ignoring case
        issue("PT-2", Status="Testing/PM Review"),  # built-in translation
        issue("PT-3", Status="Selected for Development"),
        issue("PT-4", Status="Waiting for QA", **{"Status category": "In Progress"}),
        issue("PT-5", Status="Mystery", **{"Status category": ""}),
        issue("PT-6", Status="Blocked"),
        issue("PT-7", Status="Done", Resolved="20/Oct/26 3:00 PM", **{"Status category": "Done"}),
        issue("PT-8", Status=""),
    )
    body = (await post_import(client, world.project, world.pm, data, dry_run=False)).json()
    assert body["failed"] == 0
    assert body["unknown_statuses"] == {
        "Testing/PM Review": "Testing",
        "Selected for Development": "To do",
        "Waiting for QA": "In progress",
        "Mystery": "To do",
    }
    assert [w["external_key"] for w in body["warnings"]] == ["PT-4", "PT-5"]  # only real fallbacks
    names = {status.id: status.name for status in await session.scalars(select(WorkflowStatus))}
    tasks = await tasks_by_external(session)
    assert {k: names[t.status_id] for k, t in tasks.items()} == {
        "PT-1": "To do",
        "PT-2": "Testing",
        "PT-3": "To do",
        "PT-4": "In progress",
        "PT-5": "To do",
        "PT-6": "Blocked",
        "PT-7": "Done",
        "PT-8": "To do",
    }
    assert tasks["PT-6"].blocked_reason == "Imported from Jira"
    assert tasks["PT-6"].blocked_at is not None
    assert tasks["PT-7"].completed_at == datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
    assert tasks["PT-1"].completed_at is None


async def test_a_project_status_with_the_jira_name_beats_the_translation(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    created = await client.post(
        f"/api/v1/projects/{world.project.id}/statuses",
        json={"name": "Testing/PM Review", "category": "in_progress"},
        headers=as_user(world.pm),
    )
    assert created.status_code == 201
    body = (
        await post_import(
            client,
            world.project,
            world.pm,
            jira_csv(issue("PT-1", Status="Testing/PM Review")),
            dry_run=False,
        )
    ).json()
    assert body["unknown_statuses"] == {}
    task = (await tasks_by_external(session))["PT-1"]
    assert task.status_id == uuid.UUID(created.json()["id"])


async def test_unknown_missing_and_ambiguous_assignees(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    twin_a = named(await make_user(session), "Twin Person")
    twin_b = named(await make_user(session), "Twin Person")
    gone = named(await make_user(session), "Gone Person")
    gone.is_active = False
    await session.flush()
    data = jira_csv(
        issue("PT-1", Assignee="Nobody Known"),
        issue("PT-2", Assignee="Twin Person"),
        issue("PT-3", Assignee="Gone Person"),
        issue("PT-4", Assignee="Jana Example"),
        issue("PT-5"),
        issue("PT-6", Assignee="aida.example"),
    )
    body = (await post_import(client, world.project, world.pm, data, dry_run=False)).json()
    assert body["unknown_assignees"] == ["Nobody Known", "Gone Person"]  # twins are not "unknown"
    messages = {w["external_key"]: w["message"] for w in body["warnings"]}
    assert "not found" in messages["PT-1"]
    assert "More than one" in messages["PT-2"]
    assert "not found" in messages["PT-3"]
    assert "PT-4" not in messages and "PT-5" not in messages and "PT-6" not in messages
    tasks = await tasks_by_external(session)
    assert [tasks[k].assignee_id for k in ("PT-1", "PT-2", "PT-3", "PT-5")] == [None] * 4
    assert tasks["PT-4"].assignee_id == world.jaya.id
    assert tasks["PT-6"].assignee_id == world.aida.id
    assert twin_a.id != twin_b.id
    assert body["members_added"] == ["Aida Example"]


async def test_assignee_is_found_by_email_first(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    data = b"Summary,Issue key,Assignee,Assignee email\nA,X-1,Wrong Name,JAYA@test.example\n"
    body = (await post_import(client, world.project, world.pm, data, dry_run=False)).json()
    assert body["warnings"] == []
    assert (await tasks_by_external(session))["X-1"].assignee_id == world.jaya.id


async def test_several_jira_projects_in_one_file_warn_but_import(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    data = jira_csv(issue("PT-1"), issue("ABC-2", **{"Project key": "ABC"}))
    body = (await post_import(client, world.project, world.pm, data)).json()
    assert body["other_projects_in_file"] == ["PT", "ABC"]
    assert body["created"] == 2


async def test_imported_tasks_show_up_everywhere(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await post_import(client, world.project, world.pm, FILE, dry_run=False)
    base = f"/api/v1/projects/{world.project.id}/tasks"
    listing = await client.get(base, headers=as_user(world.pm))
    assert listing.json()["total"] == 3
    by_key = {item["key"]: item for item in listing.json()["items"]}
    assert by_key["BFL-3"]["external_key"] == "PT-27"
    found = await client.get(base, params={"q": "pt-27"}, headers=as_user(world.pm))
    assert [item["key"] for item in found.json()["items"]] == ["BFL-3"]
    board = await client.get(base, params={"view": "board"}, headers=as_user(world.pm))
    assert board.json()["total"] == 3
    overdue = await client.get(base, params={"overdue": "true"}, headers=as_user(world.pm))
    assert [item["key"] for item in overdue.json()["items"]] == ["BFL-3"]
    mine = await client.get("/api/v1/me/tasks", headers=as_user(world.jaya))
    assert [item["key"] for item in mine.json()["items"]] == ["BFL-3"]
    detail = await client.get(
        f"/api/v1/tasks/{by_key['BFL-3']['id']}/comments", headers=as_user(world.jaya)
    )
    assert detail.status_code == 200 and len(detail.json()) == 1


async def test_export_then_import_into_another_project_keeps_the_data(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await post_import(client, world.project, world.pm, FILE, dry_run=False)
    exported = await client.get(
        f"/api/v1/projects/{world.project.id}/tasks/export", headers=as_user(world.pm)
    )
    target = await make_project(session, world.pm.id, code="NEW")
    session.add(ProjectMember(project_id=target.id, user_id=world.jaya.id))
    await session.flush()
    body = (await post_import(client, target, world.pm, exported.content, dry_run=False)).json()
    assert (body["created"], body["failed"]) == (3, 0)
    assert body["unknown_statuses"] == {}  # the status names are ours, so they match exactly

    def shape(row: dict[str, str]) -> tuple[str, ...]:
        keys = (
            "Summary",
            "Status",
            "Priority",
            "Assignee",
            "Due date",
            "Estimate",
            "Estimate unit",
        )
        return tuple(row[key] for key in keys)

    again = await client.get(
        f"/api/v1/projects/{target.id}/tasks/export", headers=as_user(world.pm)
    )
    first, second = parse(exported.content), parse(again.content)
    # compared as sets: tasks created in the same minute have no fixed order
    assert sorted(shape(dict(zip(first[0], r, strict=False))) for r in first[1:]) == sorted(
        shape(dict(zip(second[0], r, strict=False))) for r in second[1:]
    )
    copies = await session.scalars(select(Task.external_key).where(Task.project_id == target.id))
    assert sorted(k or "" for k in copies) == ["BFL-1", "BFL-2", "BFL-3"]  # the old keys


# --- permissions and errors -------------------------------------------------------------------


async def test_developers_cannot_import_and_outsiders_do_not_see_the_project(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    member = await post_import(client, world.project, world.jaya, FILE, dry_run=False)
    assert member.status_code == 403
    outsider = await post_import(client, world.project, world.outsider, FILE, dry_run=False)
    assert outsider.status_code == 404
    assert await count(session, Task) == 0


async def test_login_is_required_and_unknown_project_is_404(
    client: httpx.AsyncClient, world: World
) -> None:
    anonymous = await client.post(
        f"/api/v1/projects/{world.project.id}/tasks/import", files={"file": ("a.csv", FILE)}
    )
    assert anonymous.status_code == 401
    ghost = Project(id=uuid.uuid4(), code="XXX", name="x", created_by=world.pm.id)
    assert (await post_import(client, ghost, world.pm, FILE)).status_code == 404


async def test_archived_and_cancelled_projects_are_read_only(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.project.status = "cancelled"
    await session.flush()
    assert (await post_import(client, world.project, world.pm, FILE)).status_code == 409
    world.project.status = "active"
    world.project.archived_at = datetime.now(UTC)
    await session.flush()
    assert (await post_import(client, world.project, world.pm, FILE)).status_code == 409
    assert await count(session, Task) == 0


@pytest.mark.parametrize(
    ("data", "name", "message"),
    [
        (b"", "a.csv", "empty"),
        (b"Titel,Status\nA,B\n", "a.csv", "Summary"),
        (b"PK\x03\x04", "a.csv", "not a CSV"),
        (b"Summary\nA\n", "tasks.xlsx", "csv"),
        (("Summary\n" + "x\n" * 5001).encode(), "a.csv", "5000"),
    ],
)
async def test_unusable_files_give_422(
    client: httpx.AsyncClient, world: World, data: bytes, name: str, message: str
) -> None:
    response = await post_import(client, world.project, world.pm, data, name=name)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IMPORT_BAD_FILE"
    assert message in response.json()["error"]["message"]


async def test_missing_file_is_a_validation_error(client: httpx.AsyncClient, world: World) -> None:
    response = await client.post(
        f"/api/v1/projects/{world.project.id}/tasks/import", headers=as_user(world.pm)
    )
    assert response.status_code == 422


async def test_files_over_the_upload_limit_give_413(
    client: httpx.AsyncClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(router, "get_settings", lambda: SimpleNamespace(max_upload_mb=0))
    response = await post_import(client, world.project, world.pm, FILE)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


async def test_a_failure_while_saving_leaves_nothing_behind(
    client: httpx.AsyncClient,
    session: AsyncSession,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await session.commit()  # the test data is saved; only the import below may be undone
    jaya_id, pm_id, project_id = world.jaya.id, world.pm.id, world.project.id  # rollback expires
    calls = 0
    real = importer.activity.record

    def fail_on_second(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise IntegrityError("insert", {}, Exception("clash"))
        real(*args, **kwargs)

    monkeypatch.setattr(importer.activity, "record", fail_on_second)
    response = await post_import(client, world.project, world.pm, FILE, dry_run=False)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    for model in (Task, TaskComment, TaskAttachment, TaskActivity):
        assert await count(session, model) == 0
    await session.refresh(world.project)
    assert world.project.task_counter == 0  # the reserved numbers were rolled back too
    members = await session.scalars(
        select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
    )
    assert set(members) == {jaya_id, pm_id}  # Rita was not added either


async def test_the_report_is_capped_but_counts_are_complete(
    client: httpx.AsyncClient, world: World
) -> None:
    rows = [issue(f"PT-{n}", Priority="Urgent!!") for n in range(1, 251)]
    body = (await post_import(client, world.project, world.pm, jira_csv(*rows))).json()
    assert body["created"] == 250
    assert body["warning_count"] == 250
    assert len(body["warnings"]) == 200
    assert body["warnings"][0]["row"] == 2
