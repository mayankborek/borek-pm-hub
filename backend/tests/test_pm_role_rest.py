"""PM role, the rest (Mayank 25.11.2026): project invitations, milestone deliverable, reporter on
create, and generated reports (Figma report format: generate, preview, share, PDF)."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.invites import usable_invite
from app.change_requests.models import ChangeRequest
from app.common.enums import GlobalRole
from app.core.errors import AppError
from app.milestones.models import Milestone
from app.notifications.models import Notification
from app.organisations.models import Organisation, OrganisationAccountManager
from app.projects.models import Project, ProjectMember
from app.tasks.models import Task
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for

API = "/api/v1"
TODAY = datetime.now(UTC).date()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


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


class World:
    pm: User
    dev: User
    am: User
    contact: User
    manager: User
    org: Organisation
    project: Project  # external, client = org
    internal: Project


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.pm = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session)
    w.am = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    w.manager = await make_user(session, GlobalRole.MANAGER)
    w.pm.name, w.dev.name = "Alex Morgan", "Mia Chen"
    w.org = Organisation(name="Breco", type="client")
    session.add(w.org)
    await session.flush()
    session.add(OrganisationAccountManager(organisation_id=w.org.id, user_id=w.am.id))
    w.contact = await make_user(session, GlobalRole.CLIENT)
    w.contact.organisation_id = w.org.id
    w.project = await make_project(session, w.pm.id, code="WEB")
    w.project.name = "Website Development"
    w.project.project_type = "external"
    w.project.client_organisation_id = w.org.id
    w.internal = await make_project(session, w.pm.id, code="INT")
    session.add(ProjectMember(project_id=w.project.id, user_id=w.dev.id))
    await session.flush()
    return w


def token_of(invite: dict[str, Any]) -> str:
    return str(invite["url"]).split("#token=", 1)[1]


async def link_works(session: AsyncSession, token: str) -> bool:
    try:
        await usable_invite(session, token)
    except AppError:
        return False
    return True


# --- project invitations ----------------------------------------------------------------------


async def test_the_pm_invites_a_new_team_member_with_a_30_day_link(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    path = f"/projects/{world.project.id}/people/invite"
    body = {"kind": "team", "name": " Noah  Patel ", "email": "Noah@Borek.example"}

    out = await ok(client, world.pm, "POST", path, body)
    people = await ok(client, world.pm, "GET", f"/projects/{world.project.id}/people")
    again = await call(client, world.pm, "POST", path, body)

    assert (out["kind"], out["person"]["name"], out["person"]["email"]) == (
        "team",
        "Noah Patel",
        "noah@borek.example",
    )
    assert (out["person"]["role"], out["person"]["status"]) == ("developer", "invited")
    expires = datetime.fromisoformat(out["invite"]["expires_at"])
    assert timedelta(days=29) < expires - datetime.now(UTC) <= timedelta(days=30)
    assert await link_works(session, token_of(out["invite"]))
    team = {m["email"]: (m["project_role"], m["status"]) for m in people["team"]}
    assert team["noah@borek.example"] == ("developer", "invited")
    assert again.status_code == 409 and again.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_only_a_pm_can_be_invited_as_project_lead_and_developers_cannot_invite(
    client: httpx.AsyncClient, world: World
) -> None:
    path = f"/projects/{world.project.id}/people/invite"

    lead_dev = await call(
        client,
        world.pm,
        "POST",
        path,
        {"kind": "team", "name": "A", "email": "a@x.example", "project_role": "project_lead"},
    )
    lead_pm = await call(
        client,
        world.pm,
        "POST",
        path,
        {
            "kind": "team",
            "name": "B",
            "email": "b@x.example",
            "role": "pm",
            "project_role": "project_lead",
        },
    )
    by_dev = await call(
        client, world.dev, "POST", path, {"kind": "team", "name": "C", "email": "c@x.example"}
    )
    by_am = await call(
        client, world.am, "POST", path, {"kind": "client", "name": "D", "email": "d@x.example"}
    )

    assert lead_dev.status_code == 422
    assert lead_pm.status_code == 201
    assert lead_pm.json()["person"]["role"] == "pm"
    assert (by_dev.status_code, by_am.status_code) == (403, 403)


async def test_the_pm_invites_a_client_contact_on_an_external_project_only(
    client: httpx.AsyncClient, world: World
) -> None:
    body = {"kind": "client", "name": "Jordan Lee", "email": "jordan@breco.example"}

    out = await ok(client, world.pm, "POST", f"/projects/{world.project.id}/people/invite", body)
    people = await ok(client, world.pm, "GET", f"/projects/{world.project.id}/people")
    internal = await call(
        client, world.pm, "POST", f"/projects/{world.internal.id}/people/invite", body
    )

    assert (out["kind"], out["person"]["role"], out["person"]["status"]) == (
        "client",
        "client",
        "invited",
    )
    assert "jordan@breco.example" in {c["email"] for c in people["client_contacts"]}
    assert people["can"] == {"manage_team": True, "manage_client_contacts": True}
    assert internal.status_code == 409
    assert internal.json()["error"]["code"] == "NO_CLIENT_ORGANISATION"


async def test_resend_and_revoke_change_the_link_not_the_access(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    first = await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.project.id}/people/invite",
        {"kind": "client", "name": "Jordan", "email": "jordan@breco.example"},
    )
    person = first["person"]["id"]
    base = f"/projects/{world.project.id}/people/{person}/invite"

    second = await ok(client, world.pm, "POST", base)
    old_works = await link_works(session, token_of(first["invite"]))
    new_works = await link_works(session, token_of(second["invite"]))
    revoked = await ok(client, world.pm, "DELETE", base)
    after_revoke = await link_works(session, token_of(second["invite"]))
    third = await ok(client, world.pm, "POST", base)

    assert (old_works, new_works, after_revoke) == (False, True, False)
    assert revoked["status"] == "invite_expired" and revoked["is_active"] is True
    assert third["person"]["status"] == "invited"


async def test_people_who_joined_get_no_new_link_and_strangers_are_not_found(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.dev.password_hash = "x"
    stranger = await make_user(session)
    await session.flush()
    base = f"/projects/{world.project.id}/people"

    joined = await call(client, world.pm, "POST", f"{base}/{world.dev.id}/invite")
    joined_revoke = await call(client, world.pm, "DELETE", f"{base}/{world.dev.id}/invite")
    unknown = await call(client, world.pm, "POST", f"{base}/{stranger.id}/invite")
    am_not_here = await call(client, world.pm, "DELETE", f"{base}/{world.am.id}")

    assert joined.json()["error"]["code"] == "ALREADY_JOINED"
    assert joined_revoke.json()["error"]["code"] == "ALREADY_JOINED"
    assert (unknown.status_code, am_not_here.status_code) == (404, 404)


async def test_remove_takes_a_member_off_the_project_and_deactivates_a_client_contact(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    base = f"/projects/{world.project.id}/people"

    await ok(client, world.pm, "DELETE", f"{base}/{world.dev.id}")
    await ok(client, world.pm, "DELETE", f"{base}/{world.contact.id}")

    member = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == world.project.id, ProjectMember.user_id == world.dev.id
        )
    )
    await session.refresh(world.contact)
    assert member is None
    assert world.contact.is_active is False


# --- milestone deliverable, reporter on create ------------------------------------------------


async def test_a_milestone_has_its_own_deliverable(client: httpx.AsyncClient, world: World) -> None:
    base = f"/projects/{world.project.id}/milestones"
    created = await ok(
        client,
        world.pm,
        "POST",
        base,
        {
            "name": "Design sign-off",
            "due_date": (TODAY + timedelta(10)).isoformat(),
            "description": "Review",
            "deliverable": "  Approved UI kit  ",
        },
    )
    changed = await ok(
        client,
        world.pm,
        "PATCH",
        f"{base}/{created['id']}",
        {"version": created["version"], "deliverable": "UI kit + style guide"},
    )
    cleared = await ok(
        client,
        world.pm,
        "PATCH",
        f"{base}/{created['id']}",
        {"version": changed["version"], "deliverable": None},
    )

    assert created["deliverable"] == "Approved UI kit"
    assert changed["deliverable"] == "UI kit + style guide"
    assert cleared["deliverable"] is None


async def test_the_pm_can_choose_the_reporter_when_creating_a_task(
    client: httpx.AsyncClient, world: World
) -> None:
    path = f"/projects/{world.project.id}/tasks"

    by_pm = await ok(
        client, world.pm, "POST", path, {"title": "Fix login", "reporter_id": str(world.dev.id)}
    )
    by_dev = await call(
        client, world.dev, "POST", path, {"title": "Mine", "reporter_id": str(world.pm.id)}
    )
    self_report = await ok(
        client, world.dev, "POST", path, {"title": "Mine", "reporter_id": str(world.dev.id)}
    )

    assert by_pm["reporter"]["id"] == str(world.dev.id)
    assert by_dev.status_code == 403
    assert self_report["reporter"]["id"] == str(world.dev.id)


# --- generated reports ------------------------------------------------------------------------


def reports(w: World) -> str:
    return f"/projects/{w.project.id}/reports"


def at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, tzinfo=UTC)


async def test_a_task_report_counts_the_tasks_of_the_period(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    start, end = date(2026, 11, 9), date(2026, 11, 15)
    p, pm = world.project, world.pm.id
    await make_task(
        session, p, pm, status="Done", title="Tokens", completed_at=at(date(2026, 11, 10))
    )
    await make_task(
        session,
        p,
        pm,
        status="Code review",
        title="Visual",
        assignee_id=world.dev.id,
        due_date=date(2026, 11, 12),
    )
    await make_task(session, p, pm, status="Blocked", title="API credentials")
    await make_task(session, p, pm, status="Done", title="Old", completed_at=at(date(2026, 11, 1)))
    for task in await session.scalars(select(Task).where(Task.project_id == p.id)):
        task.created_at = at(date(2026, 11, 1))  # all made before the period ...
    later = await make_task(session, p, pm, title="Later")
    later.created_at = at(date(2026, 11, 20))  # ... except this one, made after it
    await session.flush()

    out = await ok(
        client,
        world.pm,
        "POST",
        reports(world),
        {"kind": "tasks", "period_start": start.isoformat(), "period_end": end.isoformat()},
    )

    assert (out["title"], out["period_kind"], out["client_name"]) == (
        "Task report",
        "custom",
        "Breco",
    )
    kpis = {k["key"]: k["value"] for k in out["content"]["kpis"]}
    assert kpis == {"total": "3", "completed": "1", "remaining": "2", "completion": "33%"}
    counts = {d["label"]: d["count"] for d in out["content"]["distribution"]}
    assert (counts["Done"], counts["Code review"], counts["Blocked"], counts["To do"]) == (
        1,
        1,
        1,
        0,
    )
    table = out["content"]["tables"][0]
    assert table["columns"] == ["Task", "Status", "Assignee", "Due"]
    rows = {r[0].split(" · ")[1]: r for r in table["rows"]}
    assert set(rows) == {"Tokens", "Visual", "API credentials"}
    assert rows["Visual"][1:] == ["Code review", "Mia Chen", "2026-11-12"]
    assert rows["API credentials"][2] == "Unassigned"


async def test_milestone_and_change_request_reports(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    start, end = date(2026, 11, 1), date(2026, 11, 30)
    p = world.project
    session.add_all(
        [
            Milestone(
                project_id=p.id,
                code="M-01",
                name="Delivery review",
                due_date=date(2026, 11, 2),
                original_due_date=date(2026, 10, 30),
                created_by=world.pm.id,
            ),
            Milestone(
                project_id=p.id,
                code="M-02",
                name="Next year",
                due_date=date(2027, 2, 1),
                created_by=world.pm.id,
            ),
        ]
    )
    cr = ChangeRequest(
        project_id=p.id,
        code="CR-02",
        title="Extend delivery review",
        description="More time",
        submitted_by=world.contact.id,
        impact_schedule_value=3,
        impact_schedule_unit="days",
    )
    old = ChangeRequest(
        project_id=p.id, code="CR-01", title="Old", description="x", submitted_by=world.pm.id
    )
    session.add_all([cr, old])
    await session.flush()
    cr.created_at = at(date(2026, 11, 5))
    old.created_at = at(date(2026, 9, 1))
    await session.flush()
    period = {"period_start": start.isoformat(), "period_end": end.isoformat()}

    milestones = await ok(
        client, world.pm, "POST", reports(world), {"kind": "milestones", **period}
    )
    requests = await ok(
        client, world.pm, "POST", reports(world), {"kind": "change_requests", **period}
    )

    m_rows = milestones["content"]["tables"][0]["rows"]
    assert [r[0] for r in m_rows] == ["M-01 · Delivery review"]
    assert m_rows[0][2:4] == ["2026-10-30", "2026-11-02"]  # baseline -> forecast
    c_rows = requests["content"]["tables"][0]["rows"]
    assert [(r[0], r[1], r[2]) for r in c_rows] == [
        ("CR-02 · Extend delivery review", "Pending", "+3 days")
    ]


async def test_project_status_reports_are_overall_or_weekly(
    client: httpx.AsyncClient, world: World
) -> None:
    overall = await ok(client, world.pm, "POST", reports(world), {"kind": "project_status"})
    weekly = await ok(
        client,
        world.pm,
        "POST",
        reports(world),
        {"kind": "project_status", "period_kind": "weekly", "period_start": "2026-11-11"},
    )
    custom = await call(
        client,
        world.pm,
        "POST",
        reports(world),
        {
            "kind": "project_status",
            "period_kind": "custom",
            "period_start": "2026-11-11",
            "period_end": "2026-11-12",
        },
    )

    assert (overall["title"], overall["period_start"]) == ("Project status report", None)
    facts = {f["key"]: f["value"] for f in overall["content"]["facts"]}
    assert (facts["health"], facts["pm"]) == ("Not reported yet", "Alex Morgan")
    assert weekly["title"] == "Weekly project status report"
    assert (weekly["period_start"], weekly["period_end"]) == ("2026-11-09", "2026-11-15")
    assert "completed_in_period" in {k["key"] for k in weekly["content"]["kpis"]}
    assert custom.status_code == 422


async def test_other_needs_a_title_and_an_expert_summary(
    client: httpx.AsyncClient, world: World
) -> None:
    missing = await call(client, world.pm, "POST", reports(world), {"kind": "other"})
    out = await ok(
        client,
        world.pm,
        "POST",
        reports(world),
        {"kind": "other", "title": "Risk review", "summary": "All good.\nNext: launch."},
    )

    assert missing.status_code == 422
    assert (out["title"], out["summary"], out["content"]["tables"]) == (
        "Risk review",
        "All good.\nNext: launch.",
        [],
    )


async def test_sharing_decides_who_sees_a_report(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    report = await ok(client, world.pm, "POST", reports(world), {"kind": "project_status"})
    one = f"{reports(world)}/{report['id']}"
    client_list = f"/client/projects/{world.project.id}/shared-reports"

    am_before = await call(client, world.am, "GET", one)
    client_before = await ok(client, world.contact, "GET", client_list)
    shared = await ok(
        client,
        world.pm,
        "POST",
        f"{one}/share",
        {"version": report["version"], "audiences": ["client", "account_manager"]},
    )
    am_after = await ok(client, world.am, "GET", one)
    am_list = await ok(client, world.am, "GET", reports(world))
    client_after = await ok(client, world.contact, "GET", client_list)
    detail = await ok(client, world.contact, "GET", f"{client_list}/{report['id']}")
    edit_shared = await call(
        client, world.pm, "PUT", one, {"version": shared["version"], "kind": "project_status"}
    )
    dev = await call(client, world.dev, "GET", reports(world))
    notified = set(
        await session.scalars(
            select(Notification.recipient_id).where(Notification.type == "project_report.shared")
        )
    )

    assert am_before.status_code == 404 and client_before["items"] == []
    assert shared["shared_with"] == ["account_manager", "client"]
    assert am_after["id"] == report["id"] and am_list["total"] == 1
    assert [r["id"] for r in client_after["items"]] == [report["id"]]
    assert (detail["prepared_by"], detail["project_name"]) == ("Alex Morgan", "Website Development")
    assert edit_shared.json()["error"]["code"] == "REPORT_SHARED"
    assert dev.status_code == 403
    assert notified == {world.am.id, world.contact.id}

    unshared = await ok(
        client, world.pm, "POST", f"{one}/share", {"version": shared["version"], "audiences": []}
    )
    edited = await ok(
        client,
        world.pm,
        "PUT",
        one,
        {"version": unshared["version"], "kind": "other", "title": "Notes", "summary": "x"},
    )
    assert (edited["kind"], edited["title"]) == ("other", "Notes")
    assert (await ok(client, world.contact, "GET", client_list))["items"] == []


async def test_internal_projects_cannot_share_with_the_client(
    client: httpx.AsyncClient, world: World
) -> None:
    path = f"/projects/{world.internal.id}/reports"
    report = await ok(client, world.pm, "POST", path, {"kind": "project_status"})

    response = await call(
        client,
        world.pm,
        "POST",
        f"{path}/{report['id']}/share",
        {"version": report["version"], "audiences": ["client"]},
    )

    assert response.json()["error"]["code"] == "NO_CLIENT_PORTAL"


async def test_reports_download_as_pdf_and_archived_ones_disappear(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.project, world.pm.id, title="Ünïcode → task")
    report = await ok(
        client,
        world.pm,
        "POST",
        reports(world),
        {
            "kind": "tasks",
            "period_start": "2025-01-01",
            "period_end": "2027-12-31",
            "summary": "Looks fine.",
        },
    )
    one = f"{reports(world)}/{report['id']}"
    await ok(
        client,
        world.pm,
        "POST",
        f"{one}/share",
        {"version": report["version"], "audiences": ["client"]},
    )

    staff_pdf = await call(client, world.pm, "GET", f"{one}/pdf")
    client_pdf = await call(
        client,
        world.contact,
        "GET",
        f"/client/projects/{world.project.id}/shared-reports/{report['id']}/pdf",
    )
    await ok(client, world.pm, "DELETE", one)
    gone = await call(client, world.pm, "GET", one)
    client_gone = await ok(
        client, world.contact, "GET", f"/client/projects/{world.project.id}/shared-reports"
    )

    for pdf in (staff_pdf, client_pdf):
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")
    assert "WEB-tasks-report-" in staff_pdf.headers["content-disposition"]
    assert gone.status_code == 404 and client_gone["items"] == []
