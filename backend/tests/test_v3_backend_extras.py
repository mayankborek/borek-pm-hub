"""V3 backend items built 24.11.2026: task links (BB-17), report blocker (BB-23), next action on
delivery cards (BB-14), risks / issues / decisions + RACI (BB-20), People & Access (BB-22) and
picklists (BB-27)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.change_requests.models import ChangeRequest
from app.common.enums import GlobalRole, ProjectRole
from app.milestones.models import Milestone
from app.organisations.models import Organisation, OrganisationAccountManager
from app.projects.models import Project, ProjectMember
from app.requirements.models import Requirement
from app.tasks.models import TaskActivity
from app.users.models import User
from tests.conftest import make_project, make_task, make_user, status_by_name
from tests.test_auth import HEADER, build_app, client_for

API = "/api/v1"
TODAY = datetime.now(UTC).date()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


class World:
    admin: User
    manager: User
    pm: User
    dev: User
    am: User
    contact: User
    project: Project
    other: Project


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    acme = Organisation(name="Acme", type="client")
    session.add(acme)
    await session.flush()
    w.admin = await make_user(session, GlobalRole.ADMIN)
    w.manager = await make_user(session, GlobalRole.MANAGER)
    w.pm = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session, GlobalRole.DEVELOPER)
    w.am = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    w.contact = await make_user(session, GlobalRole.CLIENT, email="jordan@acme.example")
    w.contact.organisation_id = acme.id
    w.project = await make_project(session, w.pm.id, "WEB")
    w.project.project_type = "external"
    w.project.client_organisation_id = acme.id
    w.other = await make_project(session, w.pm.id, "OTH")
    session.add_all(
        [
            ProjectMember(
                project_id=w.project.id, user_id=w.dev.id, project_role=ProjectRole.DEVELOPER
            ),
            OrganisationAccountManager(organisation_id=acme.id, user_id=w.am.id),
        ]
    )
    await session.commit()
    return w


async def call(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any = None, **params: Any
) -> httpx.Response:
    return await client.request(
        method, API + path, headers={HEADER: str(user.id)}, json=body, params=params or None
    )


async def ok(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any = None
) -> Any:
    response = await call(client, user, method, path, body)
    assert response.status_code < 300, response.text
    return response.json() if response.content else None


# --- task links -----------------------------------------------------------------------------------


async def test_links_read_from_both_sides_and_are_written_to_both_histories(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    a = await make_task(session, world.project, world.pm.id, title="API")
    b = await make_task(session, world.project, world.pm.id, title="UI")
    await session.commit()
    link = await ok(
        client,
        world.dev,
        "POST",
        f"/tasks/{b.id}/links",
        {"kind": "is_blocked_by", "task_id": str(a.id)},
    )
    assert (link["kind"], link["label"], link["task"]["key"]) == (
        "is_blocked_by",
        "is blocked by",
        a.key,
    )
    from_a = await ok(client, world.pm, "GET", f"/tasks/{a.id}/links")
    assert [(x["kind"], x["task"]["key"]) for x in from_a] == [("blocks", b.key)]
    again = await call(
        client, world.pm, "POST", f"/tasks/{a.id}/links", {"kind": "blocks", "task_id": str(b.id)}
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "LINK_EXISTS"
    history = await session.scalars(
        select(TaskActivity.changes).where(TaskActivity.task_id.in_([a.id, b.id]))
    )
    assert sorted(h["link"][1] for h in history) == [f"blocks {b.key}", f"is blocked by {a.key}"]
    assert (
        await call(client, world.dev, "DELETE", f"/tasks/{a.id}/links/{link['id']}")
    ).status_code == 204
    assert await ok(client, world.pm, "GET", f"/tasks/{b.id}/links") == []


async def test_relates_to_is_stored_once_and_links_stay_inside_the_project(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    a = await make_task(session, world.project, world.pm.id)
    b = await make_task(session, world.project, world.pm.id)
    elsewhere = await make_task(session, world.other, world.pm.id)
    await session.commit()
    await ok(
        client,
        world.pm,
        "POST",
        f"/tasks/{a.id}/links",
        {"kind": "relates_to", "task_id": str(b.id)},
    )
    twin = await call(
        client,
        world.pm,
        "POST",
        f"/tasks/{b.id}/links",
        {"kind": "relates_to", "task_id": str(a.id)},
    )
    assert twin.status_code == 409
    assert [x["kind"] for x in await ok(client, world.pm, "GET", f"/tasks/{b.id}/links")] == [
        "relates_to"
    ]
    for target in (elsewhere.id, a.id):
        refused = await call(
            client,
            world.pm,
            "POST",
            f"/tasks/{a.id}/links",
            {"kind": "duplicates", "task_id": str(target)},
        )
        assert refused.status_code == 422
    # The Account Manager reads tasks but does not link them.
    assert (await call(client, world.am, "GET", f"/tasks/{a.id}/links")).status_code == 200
    am_link = await call(
        client, world.am, "POST", f"/tasks/{a.id}/links", {"kind": "clones", "task_id": str(b.id)}
    )
    assert am_link.status_code == 403


# --- report blocker -------------------------------------------------------------------------------


async def test_the_assignee_reports_a_blocker_in_one_call(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    other = await make_task(session, world.project, world.pm.id)
    await session.commit()
    out = await ok(
        client,
        world.dev,
        "POST",
        f"/tasks/{task.id}/report-blocker",
        {"version": task.version, "reason": "Waiting for the API key"},
    )
    assert out["status"]["category"] == "blocked"
    assert out["blocked_reason"] == "Waiting for the API key" and out["blocked_at"]
    blank = await call(
        client,
        world.dev,
        "POST",
        f"/tasks/{task.id}/report-blocker",
        {"version": 2, "reason": "  "},
    )
    assert blank.status_code == 422
    not_mine = await call(
        client,
        world.dev,
        "POST",
        f"/tasks/{other.id}/report-blocker",
        {"version": 1, "reason": "x"},
    )
    assert not_mine.status_code == 403
    notified = await ok(client, world.pm, "GET", "/me/notifications")
    assert any(n["type"] == "task.blocked" for n in notified["items"])


async def test_report_blocker_needs_a_blocked_status(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id, assignee_id=world.dev.id)
    blocked = await status_by_name(session, world.project.id, "Blocked")
    blocked.category = "in_progress"
    await session.commit()
    response = await call(
        client, world.dev, "POST", f"/tasks/{task.id}/report-blocker", {"version": 1, "reason": "x"}
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "NO_BLOCKED_STATUS"


# --- next action ----------------------------------------------------------------------------------


async def _next_action(client: httpx.AsyncClient, user: User, project: Project) -> Any:
    listed = await ok(client, user, "GET", "/projects?page_size=200")
    return next(p["next_action"] for p in listed["items"] if p["id"] == str(project.id))


async def test_next_action_picks_the_first_open_item_in_order(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    p = world.project
    assert await _next_action(client, world.pm, p) is None
    session.add(
        Milestone(
            project_id=p.id,
            code="M-02",
            name="Launch",
            due_date=TODAY + timedelta(days=9),
            created_by=world.pm.id,
        )
    )
    await session.commit()
    assert (await _next_action(client, world.pm, p))["kind"] == "next_milestone"
    session.add(
        Requirement(
            project_id=p.id,
            code="REQ-01",
            title="Login",
            status="awaiting_acceptance",
            created_by=world.pm.id,
        )
    )
    await session.commit()
    assert (await _next_action(client, world.pm, p))["code"] == "REQ-01"
    session.add(
        ChangeRequest(
            project_id=p.id,
            code="CR-01",
            title="Dark mode",
            description="Please",
            submitted_by=world.contact.id,
        )
    )
    await session.commit()
    action = await _next_action(client, world.pm, p)
    assert (action["kind"], action["status"]) == ("change_request", "pending")
    # Developers do not see change requests, so their card skips that step.
    assert (await _next_action(client, world.dev, p))["kind"] == "client_acceptance"
    session.add(
        Milestone(
            project_id=p.id,
            code="M-01",
            name="Design",
            due_date=TODAY - timedelta(days=2),
            created_by=world.pm.id,
        )
    )
    await session.commit()
    action = await _next_action(client, world.pm, p)
    assert (action["kind"], action["code"], action["status"]) == (
        "overdue_milestone",
        "M-01",
        "late",
    )
    card = await ok(client, world.manager, "GET", "/portfolio")
    assert next(i for i in card["items"] if i["id"] == str(p.id))["next_action"]["code"] == "M-01"


# --- registers + RACI -----------------------------------------------------------------------------


async def test_risks_issues_and_decisions_keep_their_own_fields(
    client: httpx.AsyncClient, world: World
) -> None:
    base = f"/projects/{world.project.id}"
    low = await ok(
        client,
        world.pm,
        "POST",
        f"{base}/risks",
        {"title": "Minor", "probability": "low", "impact": "medium"},
    )
    high = await ok(
        client,
        world.pm,
        "POST",
        f"{base}/risks",
        {
            "title": "Vendor late",
            "probability": "high",
            "impact": "high",
            "owner_id": str(world.dev.id),
            "mitigation": "Second vendor",
        },
    )
    assert (low["code"], low["status"], low["score"]) == ("R-01", "open", 2)
    assert (high["code"], high["score"], high["owner"]["id"]) == ("R-02", 9, str(world.dev.id))
    listed = await ok(client, world.dev, "GET", f"{base}/risks")
    assert [r["code"] for r in listed["items"]] == ["R-02", "R-01"] and listed["counts"] == {
        "open": 2
    }
    wrong = await call(
        client, world.pm, "POST", f"{base}/issues", {"title": "x", "probability": "low"}
    )
    assert wrong.status_code == 422
    bad_status = await call(
        client, world.pm, "POST", f"{base}/decisions", {"title": "x", "status": "open"}
    )
    assert bad_status.status_code == 422
    issue = await ok(
        client,
        world.pm,
        "POST",
        f"{base}/issues",
        {
            "title": "Login fails",
            "priority": "high",
            "due_date": (TODAY - timedelta(days=1)).isoformat(),
        },
    )
    assert (issue["code"], issue["overdue"]) == ("I-01", True)
    resolved = await ok(
        client,
        world.pm,
        "PATCH",
        f"{base}/issues/{issue['id']}",
        {"version": issue["version"], "status": "resolved"},
    )
    assert resolved["overdue"] is False
    decision = await ok(
        client,
        world.pm,
        "POST",
        f"{base}/decisions",
        {
            "title": "Use Azure",
            "status": "decided",
            "decided_on": "2026-11-20",
            "decided_by": "Steering group",
            "rationale": "Same bill",
        },
    )
    assert (decision["code"], decision["decided_by"]) == ("D-01", "Steering group")
    outsider = await make_outsider(client, world)
    assert outsider == 404
    assert (
        await call(client, world.dev, "POST", f"{base}/risks", {"title": "x"})
    ).status_code == 403
    assert (await call(client, world.pm, "DELETE", f"{base}/risks/{low['id']}")).status_code == 204
    assert [r["code"] for r in (await ok(client, world.pm, "GET", f"{base}/risks"))["items"]] == [
        "R-02"
    ]
    # Another kind's id is not found on this route.
    assert (await call(client, world.pm, "GET", f"{base}/issues/{high['id']}")).status_code == 404


async def make_outsider(client: httpx.AsyncClient, world: World) -> int:
    return (
        await call(client, world.contact, "GET", f"/projects/{world.project.id}/risks")
    ).status_code


async def test_stakeholders_get_a_raci_role_and_communication_role(
    client: httpx.AsyncClient, world: World
) -> None:
    base = f"/projects/{world.project.id}/stakeholders"
    created = await ok(
        client,
        world.pm,
        "POST",
        base,
        {"name": "Sam", "raci": "accountable", "communication_role": "Weekly report"},
    )
    assert (created["raci"], created["communication_role"]) == ("accountable", "Weekly report")
    changed = await ok(
        client,
        world.pm,
        "PATCH",
        f"{base}/{created['id']}",
        {"version": created["version"], "raci": "informed"},
    )
    assert changed["raci"] == "informed"
    assert (
        await call(client, world.pm, "POST", base, {"name": "X", "raci": "boss"})
    ).status_code == 422


# --- people & access ------------------------------------------------------------------------------


async def test_people_lists_team_account_managers_and_client_contacts_with_status(
    client: httpx.AsyncClient, world: World
) -> None:
    out = await ok(client, world.pm, "GET", f"/projects/{world.project.id}/people")
    assert {(m["id"], m["project_role"]) for m in out["team"]} == {
        (str(world.pm.id), "project_lead"),
        (str(world.dev.id), "developer"),
    }
    assert [a["id"] for a in out["account_managers"]] == [str(world.am.id)]
    assert [(c["email"], c["status"]) for c in out["client_contacts"]] == [
        ("jordan@acme.example", "invite_expired")
    ]
    # the PM may invite / remove client contacts (Mayank 25.11.2026)
    assert out["can"] == {"manage_team": True, "manage_client_contacts": True}
    am_view = await ok(client, world.am, "GET", f"/projects/{world.project.id}/people")
    assert am_view["can"]["manage_team"] is False
    assert (
        await call(client, world.dev, "GET", f"/projects/{world.project.id}/people")
    ).status_code == 403
    internal = await ok(client, world.pm, "GET", f"/projects/{world.other.id}/people")
    assert internal["client_contacts"] == [] and internal["account_managers"] == []


# --- picklists ------------------------------------------------------------------------------------


async def test_the_administrator_edits_picklists_workflow_lists_are_protected(
    client: httpx.AsyncClient, world: World
) -> None:
    added = await ok(
        client,
        world.admin,
        "POST",
        "/admin/picklists/project_category/values",
        {"value": "Website"},
    )
    duplicate = await call(
        client,
        world.admin,
        "POST",
        "/admin/picklists/project_category/values",
        {"value": "website"},
    )
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "DUPLICATE_VALUE"
    protected = await call(
        client, world.admin, "POST", "/admin/picklists/task_priority/values", {"value": "urgent"}
    )
    assert (
        protected.status_code == 409 and protected.json()["error"]["code"] == "PICKLIST_PROTECTED"
    )
    unknown = await call(
        client, world.admin, "POST", "/admin/picklists/colours/values", {"value": "red"}
    )
    assert unknown.status_code == 404
    assert (
        await call(
            client, world.pm, "POST", "/admin/picklists/project_category/values", {"value": "x"}
        )
    ).status_code == 403

    lists = {p["key"]: p for p in await ok(client, world.pm, "GET", "/picklists")}
    assert [v["value"] for v in lists["project_category"]["values"]] == ["Website"]
    assert lists["task_priority"]["protected"] and len(lists["task_priority"]["values"]) == 5
    suggestions = await ok(client, world.pm, "GET", "/projects/categories")
    assert {"name": "Website", "project_count": 0} in suggestions

    hidden = await ok(
        client,
        world.admin,
        "PATCH",
        f"/admin/picklists/project_category/values/{added['id']}",
        {"version": added["version"], "is_active": False},
    )
    assert hidden["is_active"] is False
    lists = {p["key"]: p for p in await ok(client, world.pm, "GET", "/picklists")}
    assert lists["project_category"]["values"] == []
    admin_lists = {p["key"]: p for p in await ok(client, world.admin, "GET", "/picklists")}
    assert len(admin_lists["project_category"]["values"]) == 1
    assert (await call(client, world.contact, "GET", "/picklists")).status_code == 403
