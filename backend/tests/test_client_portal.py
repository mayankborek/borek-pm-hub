"""Client portal (/client/...) and own profile (/me/profile).

A client sees only the external, not archived projects of their own organisation, only published
status reports, and never tasks, effort, activity, drafts or money.
"""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_access_token
from app.common.enums import GlobalRole
from app.core.config import get_settings
from app.organisations.models import Organisation, OrganisationAccountManager
from app.projects.models import Project
from app.reporting.models import Stakeholder, StatusReport
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_admin_users import PASSWORD, SETTINGS
from tests.test_auth import HEADER, build_app, client_for

API = "/api/v1"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def as_user(user: User) -> dict[str, str]:
    return {HEADER: str(user.id)}


class World:
    acme: Organisation
    globex: Organisation
    contact: User  # client contact of Acme
    pm: User
    am: User
    web: Project  # Acme, external
    old: Project  # Acme, external, archived
    other: Project  # Globex, external
    internal: Project  # no client
    published: StatusReport
    newer: StatusReport
    draft: StatusReport
    other_report: StatusReport


def _report(project: Project, author: User, rag: str, day: int, *, published: bool) -> StatusReport:
    return StatusReport(
        project_id=project.id,
        rag=rag,
        summary=f"Summary {day}",
        achievements="Done things" if published else None,
        next_steps="Next things",
        risks="Some risk",
        report_date=date(2026, 11, day),
        state="published" if published else "draft",
        published_at=datetime(2026, 11, day, 12, tzinfo=UTC) if published else None,
        published_by=author.id if published else None,
        created_by=author.id,
    )


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.acme = Organisation(name="Acme", type="client")
    w.globex = Organisation(name="Globex", type="client")
    session.add_all([w.acme, w.globex])
    await session.flush()
    w.pm = await make_user(session, GlobalRole.PM, email="pm@borek.example")
    w.pm.name = "Alex Morgan"
    w.pm.phone = "+49 30 123"
    w.am = await make_user(session, GlobalRole.ACCOUNT_MANAGER, email="am@borek.example")
    w.am.name = "Sam Account"
    w.contact = await make_user(session, GlobalRole.CLIENT, email="jordan@acme.example")
    w.contact.organisation_id = w.acme.id
    session.add(OrganisationAccountManager(organisation_id=w.acme.id, user_id=w.am.id))
    w.web = await make_project(session, w.pm.id, "WEB")
    w.old = await make_project(session, w.pm.id, "OLD")
    w.other = await make_project(session, w.pm.id, "OTH")
    w.internal = await make_project(session, w.pm.id, "INT")
    for project, org in ((w.web, w.acme), (w.old, w.acme), (w.other, w.globex)):
        project.project_type = "external"
        project.client_organisation_id = org.id
    w.web.category = "Web Development"
    w.old.archived_at = datetime.now(UTC)
    await make_task(session, w.web, w.pm.id, status="Done")
    await make_task(session, w.web, w.pm.id)
    session.add(
        Stakeholder(
            project_id=w.web.id,
            name="Pat Sponsor",
            role_title="Sponsor",
            email="pat@acme.example",
            influence="high",
            notes="Internal note: hard to convince",
            created_by=w.pm.id,
        )
    )
    w.published = _report(w.web, w.pm, "green", 1, published=True)
    w.newer = _report(w.web, w.pm, "amber", 8, published=True)
    w.draft = _report(w.web, w.pm, "red", 15, published=False)
    w.other_report = _report(w.other, w.pm, "red", 9, published=True)
    session.add_all([w.published, w.newer, w.draft, w.other_report])
    await session.flush()
    return w


async def get(client: httpx.AsyncClient, user: User, path: str) -> httpx.Response:
    return await client.get(API + path, headers=as_user(user))


# --- what a client sees ------------------------------------------------------------------------


async def test_portal_lists_only_the_clients_own_external_active_projects(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await get(client, world.contact, "/client/portal")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organisation"] == {"id": str(world.acme.id), "name": "Acme"}
    assert [p["code"] for p in body["projects"]] == ["WEB"]
    project = body["projects"][0]
    assert project["category"] == "Web Development"
    assert project["health"] == "at_risk"  # newest PUBLISHED report is amber; the red draft is not
    assert project["published_on"] == "2026-11-08"
    assert project["published_by"] == {"name": "Alex Morgan", "role": "Project Manager"}
    assert project["latest_update"]["text"] == "Summary 8"
    assert project["progress"] == 50  # one of two tasks done
    assert body["summary"] == {"total": 1, "on_track": 0, "at_risk": 1, "off_track": 0, "none": 0}
    assert [u["report_id"] for u in body["updates"]] == [
        str(world.newer.id),
        str(world.published.id),
    ]


async def test_a_project_without_a_published_report_has_no_health(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.newer.archived_at = world.published.archived_at = datetime.now(UTC)
    await session.flush()

    project = (await get(client, world.contact, "/client/portal")).json()["projects"][0]

    assert project["health"] is None
    assert project["latest_update"] is None
    assert project["published_by"] is None


async def test_project_overview_has_contacts_and_published_reports_only(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await get(client, world.contact, f"/client/projects/{world.web.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contacts"] == [
        {
            "name": "Alex Morgan",
            "role": "Project Manager",
            "email": "pm@borek.example",
            "phone": "+49 30 123",
        },
        {
            "name": "Sam Account",
            "role": "Account Manager",
            "email": "am@borek.example",
            "phone": None,
        },
        {"name": "Pat Sponsor", "role": "Sponsor", "email": "pat@acme.example", "phone": None},
    ]
    assert [r["id"] for r in body["reports"]] == [str(world.newer.id), str(world.published.id)]
    assert body["reports"][0]["title"] == "Status report 08.11.2026"


async def test_nothing_internal_is_in_any_client_answer(
    client: httpx.AsyncClient, world: World
) -> None:
    paths = (
        "/client/portal",
        f"/client/projects/{world.web.id}",
        f"/client/projects/{world.web.id}/reports/{world.newer.id}",
    )
    forbidden = (
        "task_summary",
        "tasks",
        "finance",
        "budget",
        "influence",
        "Internal note",
        "members",
        "draft",
        "created_by",
        "version",
    )
    for path in paths:
        text = (await get(client, world.contact, path)).text
        for word in forbidden:
            assert word not in text, (path, word)


async def test_other_clients_internal_and_archived_projects_are_not_found(
    client: httpx.AsyncClient, world: World
) -> None:
    for project in (world.other, world.internal, world.old):
        response = await get(client, world.contact, f"/client/projects/{project.id}")
        assert response.status_code == 404, project.code
        assert response.json()["error"]["message"] == "Project not found."


async def test_report_detail_and_pdf(client: httpx.AsyncClient, world: World) -> None:
    base = f"/client/projects/{world.web.id}/reports/{world.newer.id}"

    detail = await get(client, world.contact, base)
    pdf = await get(client, world.contact, f"{base}/pdf")

    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["health"] == "at_risk"
    assert body["next_steps"] == "Next things"
    assert body["project_name"] == world.web.name
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"] == (
        'attachment; filename="status-report-2026-11-08.pdf"'
    )
    assert pdf.content.startswith(b"%PDF")


async def test_drafts_and_other_projects_reports_are_not_found(
    client: httpx.AsyncClient, world: World
) -> None:
    web = f"/client/projects/{world.web.id}/reports"
    for path in (
        f"{web}/{world.draft.id}",
        f"{web}/{world.draft.id}/pdf",
        f"{web}/{world.other_report.id}",
        f"/client/projects/{world.other.id}/reports/{world.other_report.id}",
    ):
        assert (await get(client, world.contact, path)).status_code == 404, path


async def test_a_client_without_an_organisation_sees_nothing(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    loner = await make_user(session, GlobalRole.CLIENT)

    body = (await get(client, loner, "/client/portal")).json()

    assert body["organisation"] is None
    assert body["projects"] == []
    assert (await get(client, loner, f"/client/projects/{world.web.id}")).status_code == 404


async def test_a_deactivated_client_is_refused(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.contact.is_active = False
    await session.flush()

    response = await get(client, world.contact, "/client/portal")

    assert response.status_code in (401, 403)


async def test_clients_stay_out_of_the_internal_api(
    client: httpx.AsyncClient, world: World
) -> None:
    for path in (
        "/projects",
        f"/projects/{world.web.id}",
        f"/projects/{world.web.id}/tasks",
        f"/projects/{world.web.id}/status-reports",
        "/tasks",
        "/dashboard",
        "/portfolio",
    ):
        response = await get(client, world.contact, path)
        assert response.status_code in (403, 404), path


async def test_staff_do_not_use_the_client_portal(client: httpx.AsyncClient, world: World) -> None:
    for user in (world.pm, world.am):
        assert (await get(client, user, "/client/portal")).status_code == 403


# --- own profile --------------------------------------------------------------------------------


async def test_everyone_reads_their_profile_and_sets_only_their_phone(
    client: httpx.AsyncClient, world: World
) -> None:
    url = f"{API}/me/profile"
    headers = as_user(world.contact)

    profile = (await client.get(url, headers=headers)).json()
    changed = await client.patch(url, json={"phone": " +49 (30) 555-12 "}, headers=headers)
    kept = await client.patch(url, json={}, headers=headers)
    cleared = await client.patch(url, json={"phone": ""}, headers=headers)

    assert profile["email"] == "jordan@acme.example"
    assert profile["role"] == "client"
    assert profile["organisation"] == {"id": str(world.acme.id), "name": "Acme"}
    assert profile["phone"] is None
    assert changed.status_code == 200, changed.text
    assert changed.json()["phone"] == "+49 (30) 555-12"
    assert kept.json()["phone"] == "+49 (30) 555-12"
    assert cleared.json()["phone"] is None


async def test_profile_refuses_bad_phones_and_other_fields(
    client: httpx.AsyncClient, world: World
) -> None:
    url = f"{API}/me/profile"
    for body in ({"phone": "call me"}, {"phone": "1" * 51}, {"name": "New"}, {"email": "a@b.c"}):
        response = await client.patch(url, json=body, headers=as_user(world.pm))
        assert response.status_code == 422, body


async def test_profile_needs_sign_in(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"{API}/me/profile")).status_code == 401


# --- the whole flow, with real sign-in (AUTH_MODE=local) -----------------------------------------


async def test_whole_client_flow_with_real_sign_in(session: AsyncSession) -> None:
    """PM onboards a new client with a project, the contact sets a password and signs in, the PM
    publishes a status report, and the client sees it, opens it and downloads it."""
    application = build_app(session, auth_mode="local")
    application.dependency_overrides[get_settings] = lambda: SETTINGS
    pm = await make_user(session, GlobalRole.PM, email="lead@borek.example")
    pm_token, _ = create_access_token(pm.id, SETTINGS)
    as_pm = {"Authorization": f"Bearer {pm_token}"}

    async with client_for(application) as http:
        created = await http.post(
            f"{API}/projects",
            headers=as_pm,
            json={
                "code": "FLOW",
                "name": "Flow Website",
                "type": "external",
                "category": "Web",
                "new_client": {
                    "name": "Flow Ltd",
                    "contact": {"name": "Casey Client", "email": "casey@flow.example"},
                },
            },
        )
        assert created.status_code == 201, created.text
        project_id = created.json()["id"]
        token = created.json()["client_contact"]["invite"]["url"].split("#token=")[1]

        info = await http.post(f"{API}/auth/invite-info", json={"token": token})
        assert info.json()["organisation_name"] == "Flow Ltd"
        accepted = await http.post(
            f"{API}/auth/accept-invite", json={"token": token, "password": PASSWORD}
        )
        assert accepted.status_code == 200, accepted.text
        login = await http.post(
            f"{API}/auth/login", json={"email": "casey@flow.example", "password": PASSWORD}
        )
        assert login.status_code == 200, login.text
        as_client = {"Authorization": f"Bearer {login.json()['access_token']}"}
        me = (await http.get(f"{API}/auth/me", headers=as_client)).json()
        assert me["role"] == "client"

        before = (await http.get(f"{API}/client/portal", headers=as_client)).json()
        assert [p["code"] for p in before["projects"]] == ["FLOW"]
        assert before["projects"][0]["health"] is None  # nothing published yet

        report = await http.post(
            f"{API}/projects/{project_id}/status-reports",
            headers=as_pm,
            json={"rag": "green", "summary": "All good", "next_steps": "Launch"},
        )
        assert report.status_code == 201, report.text
        report_id = report.json()["id"]
        hidden = await http.get(
            f"{API}/client/projects/{project_id}/reports/{report_id}", headers=as_client
        )
        assert hidden.status_code == 404  # still a draft
        published = await http.post(
            f"{API}/projects/{project_id}/status-reports/{report_id}/publish", headers=as_pm
        )
        assert published.status_code == 200, published.text

        after = (await http.get(f"{API}/client/portal", headers=as_client)).json()
        assert after["projects"][0]["health"] == "on_track"
        detail = (await http.get(f"{API}/client/projects/{project_id}", headers=as_client)).json()
        assert detail["contacts"][0]["name"] == pm.name
        assert [r["id"] for r in detail["reports"]] == [report_id]
        pdf = await http.get(
            f"{API}/client/projects/{project_id}/reports/{report_id}/pdf", headers=as_client
        )
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        profile = await http.patch(
            f"{API}/me/profile", headers=as_client, json={"phone": "+44 20 7946"}
        )
        assert profile.json()["phone"] == "+44 20 7946"

        assert (await http.get(f"{API}/projects", headers=as_client)).status_code == 403
        assert (await http.get(f"{API}/tasks", headers=as_client)).status_code == 403
        assert (
            await http.get(f"{API}/projects/{project_id}/tasks", headers=as_client)
        ).status_code in (403, 404)
        assert (await http.get(f"{API}/client/portal", headers=as_pm)).status_code == 403
