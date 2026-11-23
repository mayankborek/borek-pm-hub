"""Manager delivery views: portfolio card fields (published progress, next milestone, stage
filter), the Manager dashboard and one project's delivery overview, with Account Manager
scoping."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole, ProjectRole
from app.organisations.models import Organisation, OrganisationAccountManager
from app.projects.models import Project, ProjectMember
from app.users.models import User
from tests.conftest import make_project, make_user
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
    outsider: User
    am: User
    contact: User
    web: Project
    other: Project
    done: Project


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


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    acme = Organisation(name="Acme", type="client")
    globex = Organisation(name="Globex", type="client")
    session.add_all([acme, globex])
    await session.flush()
    w.manager = await make_user(session, GlobalRole.MANAGER, email="boss@borek.example")
    w.pm = await make_user(session, GlobalRole.PM, email="pm@borek.example")
    w.dev = await make_user(session, GlobalRole.DEVELOPER, email="dev@borek.example")
    w.outsider = await make_user(session, GlobalRole.DEVELOPER, email="out@borek.example")
    w.am = await make_user(session, GlobalRole.ACCOUNT_MANAGER, email="am@borek.example")
    w.contact = await make_user(session, GlobalRole.CLIENT, email="jo@acme.example")
    w.contact.organisation_id = acme.id
    session.add(OrganisationAccountManager(organisation_id=acme.id, user_id=w.am.id))
    w.web = await make_project(session, w.pm.id, "WEB")
    w.other = await make_project(session, w.pm.id, "OTH")
    w.done = await make_project(session, w.pm.id, "OLD")
    w.done.status = "completed"
    for project, org in ((w.web, acme), (w.other, globex)):
        project.project_type = "external"
        project.client_organisation_id = org.id
        project.status = "active"
    w.web.target_end_date = TODAY + timedelta(days=20)
    session.add(
        ProjectMember(project_id=w.web.id, user_id=w.dev.id, project_role=ProjectRole.DEVELOPER)
    )
    await session.commit()
    return w


async def publish_report(
    client: httpx.AsyncClient, w: World, project: Project, rag: str, progress: int | None, on: str
) -> dict[str, Any]:
    base = f"/projects/{project.id}/status-reports"
    body: dict[str, Any] = {"rag": rag, "summary": "Update", "report_date": on}
    if progress is not None:
        body["progress_percent"] = progress
    draft = await ok(client, w.pm, "POST", base, body)
    result: dict[str, Any] = await ok(client, w.pm, "POST", f"{base}/{draft['id']}/publish")
    return result


async def milestone(
    client: httpx.AsyncClient, w: World, project: Project, name: str, due: str
) -> dict[str, Any]:
    result: dict[str, Any] = await ok(
        client,
        w.pm,
        "POST",
        f"/projects/{project.id}/milestones",
        {"name": name, "due_date": due, "client_visible": True},
    )
    return result


# --- portfolio cards ----------------------------------------------------------------------------


async def test_portfolio_cards_show_published_progress_and_next_milestone(
    client: httpx.AsyncClient, world: World
) -> None:
    await publish_report(client, world, world.web, "green", 40, day(-10))
    await publish_report(client, world, world.web, "amber", None, day(-1))  # no figure shared
    base = f"/projects/{world.web.id}/status-reports"
    await ok(client, world.pm, "POST", base, {"rag": "red", "summary": "x", "progress_percent": 90})
    late = await milestone(client, world, world.web, "Design", day(-2))
    await milestone(client, world, world.web, "Launch", day(5))
    reached = await milestone(client, world, world.web, "Kick-off", day(-20))
    await ok(
        client,
        world.pm,
        "PATCH",
        f"/projects/{world.web.id}/milestones/{reached['id']}",
        {"version": 1, "done": True},
    )

    body = await ok(client, world.manager, "GET", "/portfolio")

    card = {p["code"]: p for p in body["items"]}["WEB"]
    assert card["progress"]["percent"] == 40  # newest published figure, not the draft's 90
    assert card["progress"]["published_on"] == day(-10)
    assert card["progress"]["published_by"] == world.pm.name
    assert card["rag"] == "amber"  # health still comes from the newest report
    assert card["next_milestone"]["id"] == late["id"]  # a missed date is not hidden
    assert card["next_milestone"]["state"] == "late"
    assert [lead["id"] for lead in card["leads"]] == [str(world.pm.id)]
    assert {p["code"]: p for p in body["items"]}["OTH"]["progress"] is None


async def test_portfolio_stage_filter(client: httpx.AsyncClient, world: World) -> None:
    active = await ok(client, world.manager, "GET", "/portfolio?stage=active")
    completed = await ok(client, world.manager, "GET", "/portfolio?stage=completed")

    assert sorted(p["code"] for p in active["items"]) == ["OTH", "WEB"]
    assert [p["code"] for p in completed["items"]] == ["OLD"]


# --- dashboard ----------------------------------------------------------------------------------


async def test_dashboard_kpis_upcoming_and_updates(client: httpx.AsyncClient, world: World) -> None:
    await publish_report(client, world, world.web, "green", 50, day(-3))
    soon = await milestone(client, world, world.web, "Launch", day(3))
    await milestone(client, world, world.web, "Later", day(30))
    await milestone(client, world, world.other, "Review", day(10))
    raised = await ok(
        client,
        world.contact,
        "POST",
        f"/client/projects/{world.web.id}/change-requests",
        {"title": "More pages", "description": "Two more"},
    )
    await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.other.id}/change-requests",
        {"title": "Faster", "description": "x"},
    )
    await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.web.id}/change-requests/{raised['id']}/start-review",
        {"version": 1},
    )
    req = await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.web.id}/requirements",
        {"title": "Sign-in", "description": "x", "acceptance_criteria": ["Works"]},
    )
    await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.web.id}/requirements/{req['id']}/publish",
        {"version": 1},
    )

    body = await ok(client, world.manager, "GET", "/manager/dashboard")

    assert body["today"] == TODAY.isoformat()
    assert body["kpis"] == {
        "active_projects": 2,
        "shared_reports": 1,
        "upcoming_milestones": 2,
        "requests_in_review": 1,
        "requests_pending": 1,
        "awaiting_client": 1,
    }
    upcoming = body["upcoming_milestones"]
    assert [(m["name"], m["project"]["code"]) for m in upcoming] == [
        ("Launch", "WEB"),
        ("Review", "OTH"),
    ]
    assert upcoming[0]["id"] == soon["id"]
    kinds = [(u["kind"], u["status"]) for u in body["updates"]]
    assert kinds[0] == ("requirement", "awaiting_acceptance")
    assert ("change_request", "in_review") in kinds
    assert ("change_request", "pending") in kinds
    assert ("report", None) in kinds
    assert len(body["updates"]) <= 10


async def test_account_managers_see_only_their_clients(
    client: httpx.AsyncClient, world: World
) -> None:
    await milestone(client, world, world.web, "Launch", day(3))
    await milestone(client, world, world.other, "Review", day(4))

    body = await ok(client, world.am, "GET", "/manager/dashboard")
    cards = await ok(client, world.am, "GET", "/portfolio")

    assert body["kpis"]["active_projects"] == 1
    assert [m["project"]["code"] for m in body["upcoming_milestones"]] == ["WEB"]
    assert [p["code"] for p in cards["items"]] == ["WEB"]


async def test_dashboard_is_for_managers_and_account_managers(
    client: httpx.AsyncClient, world: World
) -> None:
    for user in (world.pm, world.dev, world.contact):
        assert (await call(client, user, "GET", "/manager/dashboard")).status_code == 403


# --- project overview ---------------------------------------------------------------------------


async def test_project_overview(client: httpx.AsyncClient, world: World) -> None:
    first = await publish_report(client, world, world.web, "green", 20, day(-14))
    second = await publish_report(client, world, world.web, "green", 45, day(-7))
    await publish_report(client, world, world.web, "amber", None, day(-1))
    reached = await milestone(client, world, world.web, "Kick-off", day(-10))
    nxt = await milestone(client, world, world.web, "Launch", day(4))
    await milestone(client, world, world.other, "Elsewhere", day(1))
    await ok(
        client,
        world.pm,
        "PATCH",
        f"/projects/{world.web.id}/milestones/{reached['id']}",
        {"version": 1, "done": True},
    )

    body = await ok(client, world.manager, "GET", f"/projects/{world.web.id}/overview")

    assert body["project"]["code"] == "WEB"
    assert (body["target_end_date"], body["days_left"]) == (day(20), 20)
    assert body["progress"]["percent"] == 45
    assert body["progress"]["report_id"] == second["id"]
    assert [(t["report_id"], t["percent"]) for t in body["progress_trend"]] == [
        (first["id"], 20),
        (second["id"], 45),
    ]
    assert body["milestones"] == {"done": 1, "total": 2}
    assert body["next_milestone"]["id"] == nxt["id"]
    assert body["client_actions"] == 0
    assert {e["project"]["code"] for e in body["activity"]} == {"WEB"}
    assert ("milestone", "done") in [(e["kind"], e["status"]) for e in body["activity"]]


async def test_project_overview_for_the_team_and_nobody_else(
    client: httpx.AsyncClient, world: World
) -> None:
    empty = await ok(client, world.dev, "GET", f"/projects/{world.web.id}/overview")
    assert empty["progress"] is None
    assert empty["progress_trend"] == []
    assert empty["next_milestone"] is None
    assert empty["milestones"] == {"done": 0, "total": 0}
    assert (
        await call(client, world.am, "GET", f"/projects/{world.web.id}/overview")
    ).status_code == 200
    for user, project in ((world.outsider, world.web), (world.am, world.other)):
        response = await call(client, user, "GET", f"/projects/{project.id}/overview")
        assert response.status_code == 404
    assert (
        await call(client, world.contact, "GET", f"/projects/{world.web.id}/overview")
    ).status_code == 404  # like every staff route: clients never learn the project exists
