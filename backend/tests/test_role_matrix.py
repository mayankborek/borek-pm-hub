"""S2-12: every API route x every kind of user, on the permission layer only.

The test fails when a route has no rule, so a new endpoint cannot ship without one. Behaviour lives
in the feature tests: here "ok" only means the request got past the permission checks.

Each request runs in a savepoint that is rolled back, so an allowed archive or delete does not
change what the next user sees, and the whole matrix stays fast.
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.common.enums import GlobalRole
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.finance.models import FinanceEntry, ProjectBudget
from app.main import create_app
from app.organisations.models import Organisation, OrganisationAccountManager
from app.projects.models import Project, ProjectMember
from app.reporting.models import Stakeholder, StatusReport
from app.tasks import statuses
from app.tasks.models import Task, TaskComment
from app.users.models import User
from tests.test_auth import HEADER

API = "/api/v1"
ACTORS = {
    "admin": GlobalRole.ADMIN,
    "manager": GlobalRole.MANAGER,
    "am_own": GlobalRole.ACCOUNT_MANAGER,  # the project's client is assigned to them
    "am_other": GlobalRole.ACCOUNT_MANAGER,
    "pm_lead": GlobalRole.PM,
    "pm_member": GlobalRole.PM,
    "pm_out": GlobalRole.PM,
    "dev_lead": GlobalRole.DEVELOPER,
    "dev_member": GlobalRole.DEVELOPER,  # the assignee, and author of the comment and attachment
    "dev_other": GlobalRole.DEVELOPER,
    "dev_out": GlobalRole.DEVELOPER,
    "client": GlobalRole.CLIENT,
}
# Cannot learn that the project exists: 404 on everything inside it.
OUTSIDERS = {"admin", "am_other", "pm_out", "dev_out", "client"}

READERS = {"manager", "am_own", "pm_lead", "pm_member", "dev_lead", "dev_member", "dev_other"}
WORKERS = READERS - {"am_own"}
LEADS = {"manager", "pm_lead"}
STATUS_MANAGERS = LEADS | {"dev_lead"}
ASSIGNEE = LEADS | {"dev_member"}
OWNERS = LEADS | {"dev_member"}  # lead rights, or the author of the comment or attachment
REPORTERS = LEADS | {"am_own"}
MONEY = {"manager", "am_own"}

PMS = {"pm_lead", "pm_member", "pm_out"}
DEVELOPERS = {"dev_lead", "dev_member", "dev_other", "dev_out"}
ACCOUNT_MANAGERS = {"am_own", "am_other"}
PROJECT_PEOPLE = {"manager"} | PMS | DEVELOPERS
LIST_USERS = PROJECT_PEOPLE | ACCOUNT_MANAGERS

# No role rule to test: open to everyone, or to anyone signed in.
NO_ROLE_RULE = {
    ("GET", "/auth/dev-users"),
    ("GET", "/auth/me"),
    ("POST", "/auth/login"),
    ("POST", "/auth/accept-invite"),
    ("POST", "/auth/change-password"),
}


def inside_project(allowed: set[str]) -> dict[str, str]:
    return {a: "ok" if a in allowed else "404" if a in OUTSIDERS else "403" for a in ACTORS}


def everywhere(allowed: set[str]) -> dict[str, str]:
    return {a: "ok" if a in allowed else "403" for a in ACTORS}


@dataclass
class Case:
    method: str
    path: str
    expected: dict[str, str]
    body: dict[str, Any] | None = None
    files: dict[str, Any] | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class World:
    connection: AsyncConnection
    ids: dict[str, uuid.UUID]
    values: dict[str, str]


def cases(w: World) -> list[Case]:
    v = w.values
    csv = {"file": ("t.csv", b"Issue key;Summary\nX-1;One\n", "text/csv")}
    txt = {"file": ("a.txt", b"hello", "text/plain")}
    entry = {"kind": "spend", "amount": "1", "entry_date": "2026-11-06", "description": "x"}
    p = "/projects/{project_id}"
    t = "/tasks/{task_id}"
    return [
        # projects
        Case("GET", "/projects", everywhere(LIST_USERS)),
        Case("POST", "/projects", everywhere({"manager"} | PMS), {"code": "NEW", "name": "New"}),
        Case("GET", p, inside_project(READERS)),
        Case("PATCH", p, inside_project(LEADS), {"version": 999, "name": "x"}),
        Case("DELETE", p, inside_project(LEADS)),
        Case("GET", f"{p}/members", inside_project(READERS)),
        Case("POST", f"{p}/members", inside_project(LEADS), {"user_id": v["dev_out"]}),
        Case(
            "PATCH",
            f"{p}/members/{{user_id}}",
            inside_project(LEADS),
            {"project_role": "project_lead"},
        ),
        Case("DELETE", f"{p}/members/{{user_id}}", inside_project(LEADS)),
        # statuses
        Case("GET", f"{p}/statuses", inside_project(READERS)),
        Case(
            "POST",
            f"{p}/statuses",
            inside_project(STATUS_MANAGERS),
            {"name": "New one", "category": "todo"},
        ),
        Case(
            "PUT",
            f"{p}/statuses/order",
            inside_project(STATUS_MANAGERS),
            {"status_ids": v["status_order"].split(",")},
        ),
        Case(
            "PATCH",
            f"{p}/statuses/{{status_id}}",
            inside_project(STATUS_MANAGERS),
            {"name": "Renamed"},
        ),
        Case(
            "DELETE",
            f"{p}/statuses/{{status_id}}",
            inside_project(STATUS_MANAGERS),
            params={"move_to": v["move_to"]},
        ),
        # tasks of a project
        Case("GET", f"{p}/tasks", inside_project(READERS)),
        Case("GET", f"{p}/tasks", inside_project(READERS), params={"view": "board"}),
        Case("POST", f"{p}/tasks", inside_project(WORKERS), {"title": "x"}),
        Case("GET", f"{p}/tasks/export", inside_project(READERS)),
        Case("POST", f"{p}/tasks/import", inside_project(LEADS), files=csv),
        # tasks across projects
        Case("GET", "/tasks", everywhere(LIST_USERS)),
        Case("GET", "/tasks/export", everywhere(LIST_USERS)),
        Case("GET", "/me/tasks", everywhere(PROJECT_PEOPLE)),
        # one task
        Case("GET", t, inside_project(READERS)),
        Case("PATCH", t, inside_project(LEADS), {"version": 999, "title": "x"}),
        Case("PATCH", t, inside_project(ASSIGNEE), {"version": 999, "priority": "low"}),
        Case("PATCH", t, inside_project(ASSIGNEE), {"version": 999, "status_id": v["status_id"]}),
        Case("PATCH", t, inside_project(LEADS), {"version": 999, "due_date": "2030-01-01"}),
        Case("DELETE", t, inside_project(LEADS)),
        Case(
            "PUT",
            f"{t}/assignee",
            inside_project(LEADS),
            {"version": 999, "assignee_id": v["dev_other"]},
        ),
        # task details
        Case("GET", f"{t}/activity", inside_project(READERS)),
        Case("GET", f"{t}/comments", inside_project(READERS)),
        Case("POST", f"{t}/comments", inside_project(WORKERS), {"body": "x"}),
        Case(
            "PATCH", f"{t}/comments/{{comment_id}}", inside_project({"dev_member"}), {"body": "x"}
        ),
        Case("DELETE", f"{t}/comments/{{comment_id}}", inside_project(OWNERS)),
        Case("GET", f"{t}/attachments", inside_project(READERS)),
        Case("POST", f"{t}/attachments", inside_project(WORKERS), files=txt),
        Case(
            "POST",
            f"{t}/attachments/link",
            inside_project(WORKERS),
            {"name": "doc", "url": "https://example.com/x"},
        ),
        Case("GET", f"{t}/attachments/{{attachment_id}}/download", inside_project(READERS)),
        Case("DELETE", f"{t}/attachments/{{attachment_id}}", inside_project(OWNERS)),
        # dashboards and picker
        Case("GET", "/dashboard", everywhere({"manager"} | PMS)),
        Case("GET", "/dashboard/me", everywhere(PROJECT_PEOPLE)),
        Case("GET", "/users", everywhere({"manager"} | PMS)),
        # administration
        Case("GET", "/admin/users", everywhere({"admin"})),
        Case(
            "POST",
            "/admin/users",
            everywhere({"admin"}),
            {"name": "New", "email": "new@matrix.example", "role": "developer"},
        ),
        Case("GET", "/admin/users/{user_id}", everywhere({"admin"})),
        Case("PATCH", "/admin/users/{user_id}", everywhere({"admin"}), {"name": "Renamed"}),
        Case("POST", "/admin/users/{user_id}/deactivate", everywhere({"admin"})),
        Case("POST", "/admin/users/{user_id}/activate", everywhere({"admin"})),
        Case("POST", "/admin/users/{user_id}/invite", everywhere({"admin"})),
        Case("GET", "/admin/roles", everywhere({"admin"})),
        Case("GET", "/admin/audit-events", everywhere({"admin"})),
        # organisations
        Case("GET", "/organisations", everywhere({"admin", "manager"} | PMS | ACCOUNT_MANAGERS)),
        Case("POST", "/organisations", everywhere({"admin"}), {"name": "Another"}),
        Case(
            "GET",
            "/organisations/{organisation_id}",
            everywhere({"admin", "manager"} | PMS | ACCOUNT_MANAGERS),
        ),
        Case(
            "PATCH",
            "/organisations/{organisation_id}",
            everywhere({"admin"}),
            {"version": 999, "name": "x"},
        ),
        Case("DELETE", "/organisations/{organisation_id}", everywhere({"admin"})),
        Case(
            "PUT",
            "/organisations/{organisation_id}/account-managers",
            everywhere({"admin"}),
            {"user_ids": [v["am_own"]]},
        ),
        # oversight
        Case("GET", "/portfolio", everywhere({"manager"} | ACCOUNT_MANAGERS)),
        Case("GET", "/access-overview", everywhere({"manager"})),
        Case("GET", "/access-overview/export", everywhere({"manager"})),
        # status reports
        Case("GET", f"{p}/status-reports", inside_project(READERS)),
        Case(
            "POST", f"{p}/status-reports", inside_project(REPORTERS), {"rag": "red", "summary": "x"}
        ),
        Case("GET", f"{p}/status-reports/{{report_id}}", inside_project(READERS)),
        Case(
            "PATCH",
            f"{p}/status-reports/{{draft_id}}",
            inside_project(REPORTERS),
            {"version": 999, "rag": "red"},
        ),
        Case("POST", f"{p}/status-reports/{{draft_id}}/publish", inside_project(REPORTERS)),
        Case("DELETE", f"{p}/status-reports/{{draft_id}}", inside_project(REPORTERS)),
        # stakeholders
        Case("GET", f"{p}/stakeholders", inside_project(REPORTERS)),
        Case("POST", f"{p}/stakeholders", inside_project(REPORTERS), {"name": "x"}),
        Case(
            "PATCH",
            f"{p}/stakeholders/{{stakeholder_id}}",
            inside_project(REPORTERS),
            {"version": 999, "name": "x"},
        ),
        Case("DELETE", f"{p}/stakeholders/{{stakeholder_id}}", inside_project(REPORTERS)),
        # money
        Case("GET", f"{p}/finance", inside_project(MONEY)),
        Case(
            "PUT",
            f"{p}/finance/budget",
            inside_project(MONEY),
            {"version": 999, "amount": "1"},
        ),
        Case("GET", f"{p}/finance/entries", inside_project(MONEY)),
        Case("POST", f"{p}/finance/entries", inside_project(MONEY), entry),
        Case("DELETE", f"{p}/finance/entries/{{entry_id}}", inside_project(MONEY)),
    ]


@pytest.fixture(autouse=True)
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class Holder:
    """The session of the request being made: a new one for each request."""

    session: AsyncSession


def _app(holder: Holder) -> Any:
    application = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield holder.session

    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode="dev", environment="test"
    )
    return application


def _session_on(connection: AsyncConnection) -> AsyncSession:
    return AsyncSession(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )


async def _build_world(connection: AsyncConnection) -> tuple[dict[str, uuid.UUID], dict[str, str]]:
    ids: dict[str, uuid.UUID] = {}
    async with _session_on(connection) as s:
        for name, role in ACTORS.items():
            user = User(name=name, email=f"{name}@matrix.example", global_role=role.value)
            s.add(user)
            await s.flush()
            ids[name] = user.id
        org = Organisation(name="Matrix client", type="client")
        s.add(org)
        await s.flush()
        s.add(OrganisationAccountManager(organisation_id=org.id, user_id=ids["am_own"]))
        project = Project(
            code="MTX", name="Matrix", created_by=ids["pm_lead"], client_organisation_id=org.id
        )
        s.add(project)
        await s.flush()
        rows = await statuses.create_defaults(s, project.id)
        for name, role in (
            ("pm_lead", "project_lead"),
            ("pm_member", "developer"),
            ("dev_lead", "project_lead"),
            ("dev_member", "developer"),
            ("dev_other", "developer"),
        ):
            s.add(ProjectMember(project_id=project.id, user_id=ids[name], project_role=role))
        task = Task(
            project_id=project.id,
            key="MTX-1",
            title="Matrix task",
            status_id=rows[1].id,
            created_by=ids["pm_lead"],
            assignee_id=ids["dev_member"],
        )
        s.add(task)
        await s.flush()
        comment = TaskComment(task_id=task.id, author_id=ids["dev_member"], body="Hello")
        report = StatusReport(
            project_id=project.id,
            rag="green",
            summary="Published",
            report_date=date(2026, 11, 1),
            state="published",
            published_at=datetime(2026, 11, 1, tzinfo=UTC),
            created_by=ids["pm_lead"],
        )
        draft = StatusReport(
            project_id=project.id,
            rag="green",
            summary="Draft",
            report_date=date(2026, 11, 2),
            created_by=ids["pm_lead"],
        )
        stakeholder = Stakeholder(project_id=project.id, name="Sam", created_by=ids["pm_lead"])
        budget = ProjectBudget(project_id=project.id, amount=100, currency="EUR")
        entry = FinanceEntry(
            project_id=project.id,
            kind="spend",
            amount=1,
            entry_date=date(2026, 11, 1),
            description="x",
            created_by=ids["manager"],
        )
        s.add_all([comment, report, draft, stakeholder, budget, entry])
        await s.commit()
        ids |= {
            "project_id": project.id,
            "task_id": task.id,
            "comment_id": comment.id,
            "report_id": report.id,
            "draft_id": draft.id,
            "stakeholder_id": stakeholder.id,
            "entry_id": entry.id,
            "organisation_id": org.id,
            "status_id": rows[1].id,
            "user_id": ids["dev_other"],
        }
        values = {name: str(value) for name, value in ids.items()}
        values["status_order"] = ",".join(str(r.id) for r in rows)
        values["move_to"] = str(rows[2].id)
    return ids, values


@pytest_asyncio.fixture
async def world(session: AsyncSession, test_db_url: str) -> AsyncIterator[World]:
    """`session` empties the tables. The world is rolled back with the outer transaction."""
    engine = create_async_engine(test_db_url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        ids, values = await _build_world(connection)
        yield World(connection, ids, values)
        await transaction.rollback()
    await engine.dispose()


def _classify(response: httpx.Response) -> str:
    code = response.status_code
    if code in (401, 403):
        return str(code)
    if code == 404 and response.json().get("error", {}).get("message") == "Project not found.":
        return "404"
    if code < 300 or code == 409:  # 409: past the checks, stopped by the stale version or a rule
        return "ok"
    return f"unexpected {code}: {response.text[:120]}"


def _api_routes() -> set[tuple[str, str]]:
    found = set()
    for route in create_app().routes:
        if isinstance(route, APIRoute) and route.path.startswith(API):
            found |= {(m, route.path.removeprefix(API)) for m in route.methods}
    return found


def _route_of(path: str) -> str:
    return path.replace("{draft_id}", "{report_id}")


def test_a_rule_exists_for_every_route(world_paths: set[tuple[str, str]]) -> None:
    missing = _api_routes() - world_paths - NO_ROLE_RULE
    assert not missing, f"routes without a permission rule: {sorted(missing)}"
    stale = world_paths - _api_routes()
    assert not stale, f"rules for routes that no longer exist: {sorted(stale)}"


@pytest.fixture
def world_paths() -> set[tuple[str, str]]:
    names = ("dev_out", "dev_other", "am_own", "status_id", "status_order", "move_to")
    empty = World(None, {}, dict.fromkeys(names, ""))  # type: ignore[arg-type]
    return {(c.method, _route_of(c.path)) for c in cases(empty)}


async def test_every_kind_of_user_gets_the_expected_answer_on_every_route(world: World) -> None:
    holder = Holder()
    transport = httpx.ASGITransport(app=_app(holder), raise_app_exceptions=False)
    wrong: list[str] = []
    async with httpx.AsyncClient(transport=transport, base_url="http://matrix") as http:

        async def call(case: Case, actor: str | None) -> str:
            nested = await world.connection.begin_nested()
            holder.session = _session_on(world.connection)
            path = API + case.path.format(**world.values)
            headers = {HEADER: world.values[actor]} if actor else {}
            try:
                if case.files:
                    response = await http.request(
                        case.method, path, headers=headers, files=case.files, params=case.params
                    )
                else:
                    response = await http.request(
                        case.method, path, headers=headers, json=case.body, params=case.params
                    )
            finally:
                await holder.session.close()
                await nested.rollback()
            return _classify(response)

        # The file of the download rule: made through the API and kept for every later request.
        holder.session = _session_on(world.connection)
        uploaded = await http.post(
            f"{API}/tasks/{world.values['task_id']}/attachments",
            headers={HEADER: world.values["dev_member"]},
            files={"file": ("a.txt", b"hello", "text/plain")},
        )
        await holder.session.close()
        assert uploaded.status_code == 201, uploaded.text
        world.values["attachment_id"] = uploaded.json()["id"]

        for case in cases(world):
            for actor, expected in case.expected.items():
                actual = await call(case, actor)
                if actual != expected:
                    wrong.append(f"{case.method} {case.path} as {actor}: {actual}, not {expected}")
            anonymous = await call(case, None)
            if anonymous != "401":
                wrong.append(f"{case.method} {case.path} anonymous: {anonymous}, not 401")

    assert not wrong, "\n" + "\n".join(wrong)
