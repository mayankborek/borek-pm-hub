"""BB-56: end-to-end workflows for the Client and Manager roles through the API, as the Sprint 3
"Verify Client and Manager workflows" row asks: authorized, unauthorized and empty states.

Each test walks one workflow from the first step to the last with the people who do it in real
life (PM, client contact, Manager), so a break anywhere in the chain fails here."""

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
from tests.conftest import make_project, make_task, make_user
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
    am: User
    contact: User  # Acme's client contact
    stranger: User  # Globex's client contact
    project: Project  # Acme, external
    globex: Project  # Globex, external
    internal: Project


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    acme = Organisation(name="Acme", type="client")
    globex = Organisation(name="Globex", type="client")
    session.add_all([acme, globex])
    await session.flush()
    w.manager = await make_user(session, GlobalRole.MANAGER)
    w.pm = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session, GlobalRole.DEVELOPER)
    w.am = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    w.contact = await make_user(session, GlobalRole.CLIENT, email="jordan@acme.example")
    w.contact.organisation_id = acme.id
    w.stranger = await make_user(session, GlobalRole.CLIENT, email="sam@globex.example")
    w.stranger.organisation_id = globex.id
    w.project = await make_project(session, w.pm.id, "WEB")
    w.globex = await make_project(session, w.pm.id, "GLX")
    w.internal = await make_project(session, w.pm.id, "INT")
    for project, org in ((w.project, acme), (w.globex, globex)):
        project.project_type = "external"
        project.client_organisation_id = org.id
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
    client: httpx.AsyncClient, user: User | None, method: str, path: str, body: Any = None
) -> httpx.Response:
    headers = {HEADER: str(user.id)} if user else {}
    return await client.request(method, API + path, headers=headers, json=body)


async def ok(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any = None
) -> Any:
    response = await call(client, user, method, path, body)
    assert response.status_code < 300, f"{method} {path}: {response.text}"
    return response.json() if response.content else None


async def fresh(client: httpx.AsyncClient, user: User, path: str) -> int:
    version: int = (await ok(client, user, "GET", path))["version"]
    return version


async def publish_basics(client: httpx.AsyncClient, w: World) -> dict[str, str]:
    """What a PM shares with the client: a milestone, a status report, a requirement."""
    p = f"/projects/{w.project.id}"
    shared = await ok(
        client,
        w.pm,
        "POST",
        f"{p}/milestones",
        {"name": "Design approved", "due_date": day(7), "client_visible": True},
    )
    await ok(
        client, w.pm, "POST", f"{p}/milestones", {"name": "Internal check", "due_date": day(3)}
    )
    report = await ok(
        client,
        w.pm,
        "POST",
        f"{p}/status-reports",
        {"rag": "green", "summary": "On track", "progress_percent": 40},
    )
    await ok(client, w.pm, "POST", f"{p}/status-reports/{report['id']}/publish")
    requirement = await ok(
        client,
        w.pm,
        "POST",
        f"{p}/requirements",
        {
            "title": "Sign-in page",
            "description": "Users sign in with email.",
            "acceptance_criteria": ["Wrong password shows an error"],
        },
    )
    path = f"{p}/requirements/{requirement['id']}"
    await ok(
        client,
        w.pm,
        "POST",
        f"{path}/publish",
        {"version": await fresh(client, w.pm, path)},
    )
    return {"milestone": shared["id"], "report": report["id"], "requirement": requirement["id"]}


# --- Client -----------------------------------------------------------------------------------


async def test_client_workflow_from_first_sign_in_to_a_decided_change_request(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    c = world.contact
    # Empty state: nothing shared yet.
    empty = await ok(client, c, "GET", "/client/portal")
    assert [p["code"] for p in empty["projects"]] == ["WEB"]
    assert empty["latest_report"] is None and empty["upcoming_milestones"] == []
    assert empty["projects"][0]["health"] is None and empty["projects"][0]["progress"] is None

    ids = await publish_basics(client, world)
    await make_task(session, world.project, world.pm.id, title="Internal task")
    await session.commit()

    # Dashboard and overview show the same published values.
    portal = await ok(client, c, "GET", "/client/portal")
    card = portal["projects"][0]
    assert (card["health"], card["progress"]) == ("on_track", 40)
    assert portal["kpis"]["awaiting_input"] == 1 and portal["kpis"]["shared_reports"] == 1
    assert [m["name"] for m in portal["upcoming_milestones"]] == ["Design approved"]
    overview = await ok(client, c, "GET", f"/client/projects/{world.project.id}")
    assert overview["progress"] == card["progress"]
    text = str(overview)
    assert "Internal check" not in text and "Internal task" not in text  # never leaks

    # Report detail and PDF.
    base = f"/client/projects/{world.project.id}"
    assert (await ok(client, c, "GET", f"{base}/reports/{ids['report']}"))["id"] == ids["report"]
    pdf = await call(client, c, "GET", f"{base}/reports/{ids['report']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # Acceptance against the published version.
    answer = await call(
        client,
        c,
        "POST",
        f"{base}/requirements/{ids['requirement']}/response",
        {"version_number": 1, "decision": "accepted", "comment": "Looks right"},
    )
    assert answer.status_code < 300, answer.text
    assert (await ok(client, c, "GET", "/client/portal"))["kpis"]["awaiting_input"] == 0
    pm_view = await ok(
        client, world.pm, "GET", f"/projects/{world.project.id}/requirements/{ids['requirement']}"
    )
    assert "accepted" in str(pm_view)

    # Change request: client raises, PM reviews and approves, client sees the decision.
    raised = await ok(
        client,
        c,
        "POST",
        f"{base}/change-requests",
        {
            "title": "Move design review",
            "description": "Two more weeks, please.",
            "milestone_id": ids["milestone"],
            "requested_date": day(21),
        },
    )
    assert raised["status"] == "pending"
    queue = await ok(client, world.pm, "GET", f"/projects/{world.project.id}/change-requests")
    assert [r["code"] for r in queue["items"]] == [raised["code"]]
    staff = f"/projects/{world.project.id}/change-requests/{raised['id']}"
    await ok(
        client,
        world.pm,
        "POST",
        f"{staff}/start-review",
        {"version": await fresh(client, world.pm, staff)},
    )
    await ok(
        client,
        world.pm,
        "POST",
        f"{staff}/decision",
        {"version": await fresh(client, world.pm, staff), "decision": "approved", "note": "OK"},
    )
    seen = await ok(client, c, "GET", f"{base}/change-requests/{raised['id']}")
    assert (seen["status"], seen["decision_note"]) == ("approved", "OK")
    roadmap = await ok(client, c, "GET", f"{base}/roadmap")
    assert day(21) in str(roadmap)  # the approved date moved the milestone

    # Notifications stay inside the client's projects.
    notes = await ok(client, c, "GET", "/me/notifications")
    types = {n["type"] for n in notes["items"]}
    assert "change_request.decided" in types
    assert all(
        n.get("project", {}).get("id", str(world.project.id)) == str(world.project.id)
        for n in notes["items"]
    )


async def test_client_unauthorized_paths_are_denied_by_url_and_api(
    client: httpx.AsyncClient, world: World
) -> None:
    ids = await publish_basics(client, world)
    s = world.stranger
    base = f"/client/projects/{world.project.id}"
    for path in (
        base,
        f"{base}/roadmap",
        f"{base}/reports/{ids['report']}",
        f"{base}/reports/{ids['report']}/pdf",
        f"{base}/requirements",
        f"{base}/change-requests",
    ):
        assert (await call(client, s, "GET", path)).status_code == 404, path
    assert [p["code"] for p in (await ok(client, s, "GET", "/client/portal"))["projects"]] == [
        "GLX"
    ]
    # Clients never reach staff routes, staff never reach client routes.
    for path in (
        f"/projects/{world.project.id}",
        f"/projects/{world.project.id}/tasks",
        "/portfolio",
    ):
        assert (await call(client, world.contact, "GET", path)).status_code in (403, 404), path
    for staff in (world.pm, world.manager, world.am):
        assert (await call(client, staff, "GET", "/client/portal")).status_code == 403
    assert (await call(client, None, "GET", "/client/portal")).status_code == 401
    # Internal projects never show in a portal.
    assert (
        await call(client, world.contact, "GET", f"/client/projects/{world.internal.id}")
    ).status_code == 404


async def test_a_client_without_projects_gets_an_empty_portal(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    loner_org = Organisation(name="Initech", type="client")
    session.add(loner_org)
    await session.flush()
    loner = await make_user(session, GlobalRole.CLIENT)
    loner.organisation_id = loner_org.id
    await session.commit()
    portal = await ok(client, loner, "GET", "/client/portal")
    assert portal["projects"] == [] and portal["latest_report"] is None
    assert portal["kpis"] == {
        "active_projects": 0,
        "awaiting_input": 0,
        "upcoming_milestones": 0,
        "shared_reports": 0,
    }
    assert (await ok(client, loner, "GET", "/me/notifications"))["items"] == []


# --- Manager ----------------------------------------------------------------------------------


async def test_manager_workflow_portfolio_overview_team_and_reports(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    m = world.manager
    ids = await publish_basics(client, world)
    await make_task(
        session,
        world.project,
        world.pm.id,
        assignee_id=world.dev.id,
        due_date=TODAY - timedelta(days=1),
    )
    await make_task(session, world.project, world.pm.id)  # unassigned
    await session.commit()

    dashboard = await ok(client, m, "GET", "/manager/dashboard")
    assert dashboard["kpis"]["active_projects"] == 3
    assert dashboard["kpis"]["awaiting_client"] == 1 and dashboard["kpis"]["shared_reports"] == 1
    portfolio = await ok(client, m, "GET", "/portfolio?stage=active")
    card = next(i for i in portfolio["items"] if i["id"] == str(world.project.id))
    assert card["progress"]["percent"] == 40
    assert card["next_milestone"]["name"] == "Internal check"  # Managers see every milestone
    assert card["next_action"]["kind"] == "client_acceptance"
    overview = await ok(client, m, "GET", f"/projects/{world.project.id}/overview")
    assert overview["progress"]["percent"] == card["progress"]["percent"]  # same indicator

    workload = await ok(client, m, "GET", "/manager/workload")
    dev_row = next(p for p in workload["people"] if p["person"]["id"] == str(world.dev.id))
    assert (dev_row["open"], dev_row["overdue"]) == (1, 1)
    assert workload["unassigned"]["open"] == 1
    capacity = await ok(client, m, "GET", "/manager/capacity?weeks=4")
    assert any(p["person"]["id"] == str(world.dev.id) for p in capacity["people"])

    pdf = await call(
        client, m, "GET", f"/projects/{world.project.id}/status-reports/{ids['report']}/pdf"
    )
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    people = await ok(client, m, "GET", f"/projects/{world.project.id}/people")
    assert people["can"]["manage_team"] is True
    # Membership change by the Manager takes effect at once.
    await ok(
        client,
        m,
        "DELETE",
        f"/projects/{world.project.id}/members/{world.dev.id}",
    )
    assert (
        await call(client, world.dev, "GET", f"/projects/{world.project.id}")
    ).status_code == 404


async def test_manager_routes_are_closed_to_other_roles(
    client: httpx.AsyncClient, world: World
) -> None:
    for path in ("/manager/workload", "/manager/capacity"):
        for user in (world.pm, world.dev, world.am, world.contact):
            assert (await call(client, user, "GET", path)).status_code == 403, (
                path,
                user.global_role,
            )
    for user in (world.pm, world.dev, world.contact):
        assert (await call(client, user, "GET", "/manager/dashboard")).status_code == 403
        assert (await call(client, user, "GET", "/portfolio")).status_code == 403
    # The Account Manager sees only their client's projects.
    am_cards = await ok(client, world.am, "GET", "/portfolio")
    assert [i["code"] for i in am_cards["items"]] == ["WEB"]
    assert (
        await call(client, world.am, "GET", f"/projects/{world.globex.id}/overview")
    ).status_code == 404


async def test_manager_views_without_any_data_are_empty_not_broken(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    manager = await make_user(session, GlobalRole.MANAGER)
    await session.commit()
    dashboard = await ok(client, manager, "GET", "/manager/dashboard")
    assert dashboard["upcoming_milestones"] == [] and dashboard["updates"] == []
    assert set(dashboard["kpis"].values()) == {0}
    assert (await ok(client, manager, "GET", "/portfolio"))["items"] == []
    workload = await ok(client, manager, "GET", "/manager/workload")
    assert workload["people"] == [] and workload["unassigned"]["open"] == 0
