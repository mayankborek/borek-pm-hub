"""Manager rows: staff report PDF, change request delivery, milestone alerts for leads and
Managers (moved, done, running late), the client's per-project "awaiting input", and the Manager
access model (membership changes on any project)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole, ProjectRole
from app.milestones.models import Milestone
from app.notifications.events import milestones_running_late
from app.organisations.models import Organisation
from app.projects.models import Project, ProjectMember
from app.users.models import User
from tests.conftest import make_project, make_user, status_by_name
from tests.test_auth import HEADER, build_app, client_for

API = "/api/v1"
TODAY = datetime.now(UTC).date()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


class World:
    manager: User
    pm: User
    dev: User
    newcomer: User
    contact: User
    project: Project


async def call(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any = None
) -> httpx.Response:
    return await client.request(method, API + path, headers={HEADER: str(user.id)}, json=body)


async def ok(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any = None
) -> Any:
    response = await call(client, user, method, path, body)
    assert response.status_code < 300, response.text
    return response.json() if response.content else None


async def types(client: httpx.AsyncClient, user: User) -> list[str]:
    body = await ok(client, user, "GET", "/me/notifications?limit=50")
    return [n["type"] for n in body["items"]]


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    org = Organisation(name="Acme", type="client")
    session.add(org)
    await session.flush()
    w.manager = await make_user(session, GlobalRole.MANAGER, email="boss@borek.example")
    w.pm = await make_user(session, GlobalRole.PM, email="pm@borek.example")
    w.dev = await make_user(session, GlobalRole.DEVELOPER, email="dev@borek.example")
    w.newcomer = await make_user(session, GlobalRole.DEVELOPER, email="new@borek.example")
    w.contact = await make_user(session, GlobalRole.CLIENT, email="jo@acme.example")
    w.contact.organisation_id = org.id
    w.project = await make_project(session, w.pm.id, "WEB")
    w.project.project_type = "external"
    w.project.client_organisation_id = org.id
    w.project.status = "active"
    session.add(
        ProjectMember(project_id=w.project.id, user_id=w.dev.id, project_role=ProjectRole.DEVELOPER)
    )
    await session.commit()
    return w


def base(w: World) -> str:
    return f"/projects/{w.project.id}"


# --- reports ------------------------------------------------------------------------------------


async def test_staff_download_published_reports_only(
    client: httpx.AsyncClient, world: World
) -> None:
    reports = f"{base(world)}/status-reports"
    draft = await ok(client, world.pm, "POST", reports, {"rag": "green", "summary": "Fine"})
    missing = await call(client, world.manager, "GET", f"{reports}/{draft['id']}/pdf")
    assert missing.status_code == 404
    await ok(client, world.pm, "POST", f"{reports}/{draft['id']}/publish")

    for user in (world.manager, world.dev):
        response = await call(client, user, "GET", f"{reports}/{draft['id']}/pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")
        assert "attachment" in response.headers["content-disposition"]


# --- change request delivery --------------------------------------------------------------------


async def test_change_request_delivery_follows_the_milestone(
    client: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    milestone = await ok(
        client,
        world.pm,
        "POST",
        f"{base(world)}/milestones",
        {"name": "Launch", "due_date": day(10), "client_visible": True},
    )
    crs = f"{base(world)}/change-requests"
    raised = await ok(
        client,
        world.pm,
        "POST",
        crs,
        {
            "title": "Move",
            "description": "x",
            "milestone_id": milestone["id"],
            "requested_date": day(15),
        },
    )
    plain = await ok(client, world.pm, "POST", crs, {"title": "Plain", "description": "x"})
    assert raised["delivery"] is None  # not approved yet

    async def decide(cr: dict[str, Any], decision: str) -> dict[str, Any]:
        reviewed = await ok(
            client, world.pm, "POST", f"{crs}/{cr['id']}/start-review", {"version": cr["version"]}
        )
        result: dict[str, Any] = await ok(
            client,
            world.pm,
            "POST",
            f"{crs}/{cr['id']}/decision",
            {"version": reviewed["version"], "decision": decision},
        )
        return result

    approved = await decide(raised, "approved")
    assert approved["delivery"] == "not_started"
    assert (await decide(plain, "approved"))["delivery"] is None  # no milestone

    task = await ok(
        client,
        world.pm,
        "POST",
        f"{base(world)}/tasks",
        {"title": "Build it", "milestone_id": milestone["id"], "assignee_id": str(world.dev.id)},
    )
    started = await status_by_name(session, world.project.id, "In progress")
    await ok(
        client,
        world.dev,
        "PATCH",
        f"/tasks/{task['id']}",
        {"version": task["version"], "status_id": str(started.id)},
    )
    assert (await ok(client, world.manager, "GET", f"{crs}/{raised['id']}"))[
        "delivery"
    ] == "in_progress"

    current = await ok(client, world.pm, "GET", f"{base(world)}/milestones/{milestone['id']}")
    await ok(
        client,
        world.pm,
        "PATCH",
        f"{base(world)}/milestones/{milestone['id']}",
        {"version": current["version"], "done": True},
    )
    assert (await ok(client, world.manager, "GET", f"{crs}/{raised['id']}"))["delivery"] == "done"


# --- milestone alerts for leads and Managers ----------------------------------------------------


async def test_leads_and_managers_hear_about_every_milestone(
    client: httpx.AsyncClient, world: World
) -> None:
    hidden = await ok(
        client, world.pm, "POST", f"{base(world)}/milestones", {"name": "QA", "due_date": day(5)}
    )
    path = f"{base(world)}/milestones/{hidden['id']}"
    moved = await ok(client, world.pm, "PATCH", path, {"version": 1, "due_date": day(7)})
    await ok(client, world.manager, "PATCH", path, {"version": moved["version"], "done": True})

    manager_items = await types(client, world.manager)
    pm_items = await types(client, world.pm)

    assert manager_items == ["milestone.moved"]  # the Manager did the "done" themselves
    assert pm_items == ["milestone.done"]  # the PM moved it themselves
    assert await types(client, world.contact) == []  # not shared with the client
    assert await types(client, world.dev) == []


async def test_running_late_is_reported_once_per_due_date(
    client: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    m = await ok(
        client,
        world.pm,
        "POST",
        f"{base(world)}/milestones",
        {"name": "Review", "due_date": day(3)},
    )
    await session.execute(
        update(Milestone).where(Milestone.id == m["id"]).values(due_date=TODAY - timedelta(days=2))
    )
    await session.commit()

    assert await milestones_running_late(session) == 1
    await session.commit()
    assert await milestones_running_late(session) == 0  # already told for this date
    await session.commit()

    late = (await ok(client, world.manager, "GET", "/me/notifications"))["items"][0]
    assert late["type"] == "milestone.late"
    assert late["params"]["days_late"] == 2
    assert await types(client, world.pm) == ["milestone.late"]
    assert await types(client, world.contact) == []

    await session.execute(
        update(Milestone).where(Milestone.id == m["id"]).values(due_date=TODAY - timedelta(days=1))
    )
    await session.commit()
    assert await milestones_running_late(session) == 1  # a new date: told again


# --- client per-project awaiting input ----------------------------------------------------------


async def test_client_project_cards_count_awaiting_input(
    client: httpx.AsyncClient, world: World
) -> None:
    req = await ok(
        client,
        world.pm,
        "POST",
        f"{base(world)}/requirements",
        {"title": "Sign-in", "description": "x", "acceptance_criteria": ["Works"]},
    )
    await ok(
        client, world.pm, "POST", f"{base(world)}/requirements/{req['id']}/publish", {"version": 1}
    )

    portal = await ok(client, world.contact, "GET", "/client/portal")

    assert [p["awaiting_input"] for p in portal["projects"]] == [1]
    assert portal["kpis"]["awaiting_input"] == 1


# --- Manager access model -----------------------------------------------------------------------


async def test_managers_change_membership_on_any_project(
    client: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    members = f"{base(world)}/members"

    async def sees(user: User) -> int:
        status = (await call(client, user, "GET", base(world))).status_code
        # The tests share one session: a refused request rolls it back, so load the row again
        # (each real request has its own session).
        await session.refresh(world.project)
        return status

    assert await sees(world.newcomer) == 404
    await ok(client, world.manager, "POST", members, {"user_id": str(world.newcomer.id)})
    assert await sees(world.newcomer) == 200  # applies to the next access check at once

    await ok(
        client,
        world.manager,
        "PATCH",
        f"{members}/{world.newcomer.id}",
        {"project_role": "project_lead"},
    )
    roles = {
        m["user_id"]: m["project_role"] for m in await ok(client, world.manager, "GET", members)
    }
    assert roles[str(world.newcomer.id)] == "project_lead"

    await ok(client, world.manager, "DELETE", f"{members}/{world.newcomer.id}")
    assert await sees(world.newcomer) == 404


async def test_the_last_lead_stays_and_others_cannot_change_membership(
    client: httpx.AsyncClient, world: World
) -> None:
    members = f"{base(world)}/members"
    last = await call(client, world.manager, "DELETE", f"{members}/{world.pm.id}")
    assert last.status_code == 409
    assert last.json()["error"]["code"] == "LAST_PROJECT_LEAD"
    demote = await call(
        client, world.manager, "PATCH", f"{members}/{world.pm.id}", {"project_role": "developer"}
    )
    assert demote.status_code == 409

    refused = await call(client, world.dev, "POST", members, {"user_id": str(world.newcomer.id)})
    assert refused.status_code == 403
    outsider = await call(
        client, world.newcomer, "POST", members, {"user_id": str(world.newcomer.id)}
    )
    assert outsider.status_code == 404


# --- "Milestone schedule published" in Recent updates ------------------------------------------


async def test_shared_milestones_appear_in_recent_updates(
    client: httpx.AsyncClient, world: World
) -> None:
    ms = f"{base(world)}/milestones"
    hidden = await ok(client, world.pm, "POST", ms, {"name": "QA", "due_date": day(5)})
    shared = await ok(
        client, world.pm, "POST", ms, {"name": "Launch", "due_date": day(9), "client_visible": True}
    )

    def milestone_events(items: list[dict[str, Any]]) -> list[tuple[str, str, str | None]]:
        return [(e["title"], e["status"], e["due_date"]) for e in items if e["kind"] == "milestone"]

    staff = (await ok(client, world.manager, "GET", "/manager/dashboard"))["updates"]
    assert milestone_events(staff) == [(f"{shared['code']} Launch", "shared", day(9))]
    portal = (await ok(client, world.contact, "GET", "/client/portal"))["updates"]
    assert [(e["milestone_id"], e["status"], e["due_date"]) for e in portal] == [
        (shared["id"], "shared", day(9))
    ]

    # Shared later: the event takes that moment; reached: a second event.
    path = f"{ms}/{hidden['id']}"
    now_shared = await ok(client, world.pm, "PATCH", path, {"version": 1, "client_visible": True})
    await ok(client, world.pm, "PATCH", path, {"version": now_shared["version"], "done": True})
    activity = (await ok(client, world.contact, "GET", f"/client/projects/{world.project.id}"))[
        "activity"
    ]
    assert [(e["title"], e["status"]) for e in activity][:3] == [
        (f"{hidden['code']} QA", "done"),
        (f"{hidden['code']} QA", "shared"),
        (f"{shared['code']} Launch", "shared"),
    ]

    # Hidden again: gone for the client, and no "shared" event on the staff side either.
    current = await ok(client, world.pm, "GET", f"{ms}/{shared['id']}")
    await ok(
        client,
        world.pm,
        "PATCH",
        f"{ms}/{shared['id']}",
        {"version": current["version"], "client_visible": False},
    )
    portal = (await ok(client, world.contact, "GET", "/client/portal"))["updates"]
    assert all(e["milestone_id"] != shared["id"] for e in portal)
    overview = (await ok(client, world.manager, "GET", f"{base(world)}/overview"))["activity"]
    assert (f"{shared['code']} Launch", "shared", day(9)) not in milestone_events(overview)


# --- search in the change request and report libraries ------------------------------------------


async def test_change_requests_can_be_searched_by_code_or_title(
    client: httpx.AsyncClient, world: World
) -> None:
    crs = f"{base(world)}/change-requests"
    first = await ok(client, world.pm, "POST", crs, {"title": "Extend review", "description": "x"})
    await ok(client, world.pm, "POST", crs, {"title": "New logo", "description": "x"})

    by_title = await ok(client, world.manager, "GET", f"{crs}?q=REVIEW")
    by_code = await ok(client, world.manager, "GET", f"{crs}?q={first['code'].lower()}")
    none = await ok(client, world.manager, "GET", f"{crs}?q=nothing&status=pending")

    assert [r["title"] for r in by_title["items"]] == ["Extend review"]
    assert [r["id"] for r in by_code["items"]] == [first["id"]]
    assert (none["items"], none["total"]) == ([], 0)
    assert by_title["counts"]["total"] == 2  # counts stay over every request (filter tabs)


async def test_reports_can_be_searched_by_text_or_date(
    client: httpx.AsyncClient, world: World
) -> None:
    reports = f"{base(world)}/status-reports"
    for summary, date_ in (("Design signed off", "2026-10-02"), ("Testing 50% done", "2026-11-06")):
        r = await ok(
            client,
            world.pm,
            "POST",
            reports,
            {"rag": "green", "summary": summary, "report_date": date_},
        )
        await ok(client, world.pm, "POST", f"{reports}/{r['id']}/publish")

    async def found(q: str) -> list[str]:
        body = await ok(client, world.manager, "GET", f"{reports}?q={q}")
        return [r["summary"] for r in body["items"]]

    assert await found("signed") == ["Design signed off"]
    assert await found("06.11.2026") == ["Testing 50% done"]
    assert await found("2026-10") == ["Design signed off"]
    assert await found("n%25d") == []  # % is literal: as a wildcard it would match both
    assert await found("zzz") == []
