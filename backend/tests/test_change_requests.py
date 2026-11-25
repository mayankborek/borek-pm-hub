"""Change requests: raise, fill in impact, decide; the milestone move on approval; the client's
view and the access rules."""

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
    pm: User
    am: User
    dev: User
    contact: User
    project: Project
    other: Project
    shown: dict[str, Any]  # milestone visible to the client
    hidden: dict[str, Any]


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
async def world(client: httpx.AsyncClient, session: AsyncSession) -> World:
    w = World()
    acme = Organisation(name="Acme", type="client")
    globex = Organisation(name="Globex", type="client")
    session.add_all([acme, globex])
    await session.flush()
    w.pm = await make_user(session, GlobalRole.PM, email="pm@borek.example")
    w.am = await make_user(session, GlobalRole.ACCOUNT_MANAGER, email="am@borek.example")
    w.dev = await make_user(session, GlobalRole.DEVELOPER, email="dev@borek.example")
    w.contact = await make_user(session, GlobalRole.CLIENT, email="jordan@acme.example")
    w.contact.name = "Jordan Lee"
    w.contact.organisation_id = acme.id
    session.add(OrganisationAccountManager(organisation_id=acme.id, user_id=w.am.id))
    w.project = await make_project(session, w.pm.id, "WEB")
    w.other = await make_project(session, w.pm.id, "OTH")
    for project, org in ((w.project, acme), (w.other, globex)):
        project.project_type = "external"
        project.client_organisation_id = org.id
    session.add(
        ProjectMember(project_id=w.project.id, user_id=w.dev.id, project_role=ProjectRole.DEVELOPER)
    )
    await session.flush()
    base = f"/projects/{w.project.id}/milestones"
    w.shown = await ok(
        client,
        w.pm,
        "POST",
        base,
        {"name": "Delivery review", "due_date": day(5), "client_visible": True},
    )
    w.hidden = await ok(client, w.pm, "POST", base, {"name": "Internal QA", "due_date": day(8)})
    return w


def crs(w: World) -> str:
    return f"/projects/{w.project.id}/change-requests"


def client_crs(w: World) -> str:
    return f"/client/projects/{w.project.id}/change-requests"


async def milestone(client: httpx.AsyncClient, w: World, m: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = await ok(
        client, w.pm, "GET", f"/projects/{w.project.id}/milestones/{m['id']}"
    )
    return result


async def raise_move(client: httpx.AsyncClient, w: World, to: int) -> dict[str, Any]:
    result: dict[str, Any] = await ok(
        client,
        w.contact,
        "POST",
        client_crs(w),
        {
            "title": "Extend delivery review",
            "description": "We need two more weeks.",
            "reason": "Content late",
            "milestone_id": w.shown["id"],
            "requested_date": day(to),
        },
    )
    return result


async def review(client: httpx.AsyncClient, w: World, request_id: str) -> dict[str, Any]:
    """pending -> in_review, with the current version."""
    current = await ok(client, w.pm, "GET", f"{crs(w)}/{request_id}")
    result: dict[str, Any] = await ok(
        client,
        w.pm,
        "POST",
        f"{crs(w)}/{request_id}/start-review",
        {"version": current["version"]},
    )
    return result


async def decide(
    client: httpx.AsyncClient, w: World, request_id: str, decision: str, note: str | None = None
) -> dict[str, Any]:
    """Start the review if needed, then decide, always with the current version."""
    current = await ok(client, w.pm, "GET", f"{crs(w)}/{request_id}")
    if current["status"] == "pending":
        current = await review(client, w, request_id)
    result: dict[str, Any] = await ok(
        client,
        w.pm,
        "POST",
        f"{crs(w)}/{request_id}/decision",
        {"version": current["version"], "decision": decision, "note": note},
    )
    return result


# --- raising ------------------------------------------------------------------------------------


async def test_staff_raise_requests_with_codes_and_counts(
    client: httpx.AsyncClient, world: World
) -> None:
    first = await ok(client, world.pm, "POST", crs(world), {"title": "A", "description": "a"})
    second = await ok(client, world.am, "POST", crs(world), {"title": "B", "description": "b"})

    listed = await ok(client, world.am, "GET", crs(world))

    assert (first["code"], second["code"]) == ("CR-01", "CR-02")
    assert first["status"] == "pending"
    assert first["submitted_by_client"] is False
    assert [r["code"] for r in listed["items"]] == ["CR-02", "CR-01"]
    assert listed["counts"] == {
        "total": 2,
        "pending": 2,
        "in_review": 0,
        "approved": 0,
        "declined": 0,
    }


async def test_client_raises_a_milestone_move(client: httpx.AsyncClient, world: World) -> None:
    raised = await raise_move(client, world, 19)

    assert raised["code"] == "CR-01"
    assert raised["milestone"] == {"code": "M-01", "name": "Delivery review"}
    assert raised["submitted_by"] == "Jordan Lee"
    m = await milestone(client, world, world.shown)
    assert (m["requested_date"], m["change_request_code"]) == (day(19), "CR-01")
    assert m["due_date"] == day(5)  # nothing moves before a decision
    staff = await ok(client, world.pm, "GET", f"{crs(world)}/{raised['id']}")
    assert staff["submitted_by_client"] is True


async def test_client_cannot_pick_a_hidden_milestone(
    client: httpx.AsyncClient, world: World
) -> None:
    hidden = await call(
        client,
        world.contact,
        "POST",
        client_crs(world),
        {"title": "x", "description": "y", "milestone_id": world.hidden["id"]},
    )
    no_milestone = await call(
        client,
        world.contact,
        "POST",
        client_crs(world),
        {"title": "x", "description": "y", "requested_date": day(3)},
    )

    assert hidden.status_code == 422
    assert hidden.json()["error"]["details"][0]["issue"] == "unknown_milestone"
    assert no_milestone.status_code == 422


# --- impact and decision ------------------------------------------------------------------------


async def test_lead_fills_in_impact_and_approves_which_moves_the_milestone(
    client: httpx.AsyncClient, world: World
) -> None:
    raised = await raise_move(client, world, 19)
    path = f"{crs(world)}/{raised['id']}"
    assessed = await ok(
        client,
        world.pm,
        "PATCH",
        path,
        {
            "version": 1,
            "impact_schedule_value": 2,
            "impact_schedule_unit": "weeks",
            "impact_effort_value": 40,
            "impact_effort_unit": "hours",
            "impact_scope": "Two more review rounds",
        },
    )

    assert (assessed["impact_schedule_value"], assessed["impact_schedule_unit"]) == (2, "weeks")
    assert (assessed["impact_effort_value"], assessed["impact_effort_unit"]) == (40, "hours")
    approved = await decide(client, world, raised["id"], "approved", "Agreed in the call")

    assert approved["status"] == "approved"
    assert approved["decided_by"]["id"] == str(world.pm.id)
    assert approved["decided_at"] is not None
    m = await milestone(client, world, world.shown)
    assert (m["due_date"], m["original_due_date"], m["state"]) == (day(19), day(5), "revised")
    assert (m["requested_date"], m["change_request_code"]) == (None, "CR-01")
    roadmap = await ok(client, world.contact, "GET", f"/client/projects/{world.project.id}/roadmap")
    shown = roadmap["unphased_milestones"][0]
    assert (shown["state"], shown["due_date"], shown["original_due_date"]) == (
        "revised",
        day(19),
        day(5),
    )


async def test_a_second_approval_keeps_the_first_original_date(
    client: httpx.AsyncClient, world: World
) -> None:
    for to in (19, 26):
        raised = await raise_move(client, world, to)
        await decide(client, world, raised["id"], "approved")

    m = await milestone(client, world, world.shown)

    assert (m["due_date"], m["original_due_date"], m["change_request_code"]) == (
        day(26),
        day(5),
        "CR-02",
    )


async def test_declining_leaves_the_milestone_alone(
    client: httpx.AsyncClient, world: World
) -> None:
    raised = await raise_move(client, world, 19)

    declined = await decide(client, world, raised["id"], "declined", "Date is fixed by the launch")

    assert declined["status"] == "declined"
    m = await milestone(client, world, world.shown)
    assert (m["due_date"], m["original_due_date"], m["state"]) == (day(5), None, "planned")
    assert (m["requested_date"], m["change_request_code"]) == (None, None)


async def test_a_decision_is_final(client: httpx.AsyncClient, world: World) -> None:
    raised = await raise_move(client, world, 19)
    path = f"{crs(world)}/{raised['id']}"
    decided = await decide(client, world, raised["id"], "declined")

    again = await call(
        client,
        world.pm,
        "POST",
        f"{path}/decision",
        {"version": decided["version"], "decision": "approved"},
    )
    edit = await call(
        client, world.pm, "PATCH", path, {"version": decided["version"], "title": "x"}
    )

    assert again.json()["error"]["code"] == "CHANGE_REQUEST_CLOSED"
    assert edit.json()["error"]["code"] == "CHANGE_REQUEST_CLOSED"


async def test_approving_a_move_of_a_reached_milestone_is_refused(
    client: httpx.AsyncClient, world: World
) -> None:
    raised = await raise_move(client, world, 19)
    await ok(
        client,
        world.pm,
        "PATCH",
        f"/projects/{world.project.id}/milestones/{world.shown['id']}",
        {"version": world.shown["version"], "done": True},
    )

    reviewed = await review(client, world, raised["id"])

    response = await call(
        client,
        world.pm,
        "POST",
        f"{crs(world)}/{raised['id']}/decision",
        {"version": reviewed["version"], "decision": "approved"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MILESTONE_DONE"


async def test_a_stale_version_is_refused(client: httpx.AsyncClient, world: World) -> None:
    raised = await raise_move(client, world, 19)
    path = f"{crs(world)}/{raised['id']}"
    await ok(
        client,
        world.pm,
        "PATCH",
        path,
        {"version": 1, "impact_schedule_value": 3, "impact_schedule_unit": "days"},
    )

    stale = await call(client, world.pm, "POST", f"{path}/start-review", {"version": 1})

    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


async def test_review_must_start_before_a_decision(client: httpx.AsyncClient, world: World) -> None:
    raised = await raise_move(client, world, 19)
    path = f"{crs(world)}/{raised['id']}"
    edited = await ok(
        client,
        world.pm,
        "PATCH",
        path,
        {"version": 1, "impact_schedule_value": 3, "impact_schedule_unit": "days"},
    )

    too_early = await call(
        client, world.pm, "POST", f"{path}/decision", {"version": 2, "decision": "approved"}
    )
    reviewed = await review(client, world, raised["id"])
    twice = await call(
        client, world.pm, "POST", f"{path}/start-review", {"version": reviewed["version"]}
    )

    assert edited["status"] == "pending"  # open requests can be edited while pending
    assert too_early.json()["error"]["code"] == "REVIEW_NOT_STARTED"
    assert reviewed["status"] == "in_review" and reviewed["review_started_at"] is not None
    assert twice.json()["error"]["code"] == "NOT_PENDING"
    m = await milestone(client, world, world.shown)
    assert m["requested_date"] == day(19)  # still asked for while in review
    shown = await ok(client, world.contact, "GET", f"{client_crs(world)}/{raised['id']}")
    assert shown["review_started_at"] is not None


# --- access -------------------------------------------------------------------------------------


async def test_who_may_do_what(client: httpx.AsyncClient, world: World) -> None:
    raised = await raise_move(client, world, 19)
    path = f"{crs(world)}/{raised['id']}"

    dev_reads = await call(client, world.dev, "GET", crs(world))
    am_assesses = await call(client, world.am, "PATCH", path, {"version": 1, "impact_scope": "x"})
    am_decides = await call(
        client, world.am, "POST", f"{path}/decision", {"version": 1, "decision": "approved"}
    )
    am_reviews = await call(client, world.am, "POST", f"{path}/start-review", {"version": 1})
    client_internal = await call(client, world.contact, "GET", crs(world))

    assert dev_reads.status_code == 403
    assert am_reviews.status_code == 403
    assert am_assesses.status_code == 403
    assert am_decides.status_code == 403
    assert client_internal.status_code in (403, 404)


# --- the client's view --------------------------------------------------------------------------


async def test_client_sees_no_effort_and_no_internal_people(
    client: httpx.AsyncClient, world: World
) -> None:
    raised = await raise_move(client, world, 19)
    path = f"{crs(world)}/{raised['id']}"
    await ok(
        client,
        world.pm,
        "PATCH",
        path,
        {
            "version": 1,
            "impact_schedule_value": 14,
            "impact_schedule_unit": "days",
            "impact_effort_value": 5,
            "impact_effort_unit": "days",
        },
    )
    await decide(client, world, raised["id"], "approved", "Fine")
    internal = await ok(
        client,
        world.pm,
        "POST",
        crs(world),
        {"title": "Internal", "description": "QA", "milestone_id": world.hidden["id"]},
    )

    listed = await ok(client, world.contact, "GET", client_crs(world))
    one = await ok(client, world.contact, "GET", f"{client_crs(world)}/{raised['id']}")
    detail = await ok(client, world.contact, "GET", f"/client/projects/{world.project.id}")

    assert "impact_effort_value" not in one and "impact_effort_unit" not in one
    assert "decided_by" not in one
    assert (
        one["impact_schedule_value"],
        one["impact_schedule_unit"],
        one["decision_note"],
        one["status"],
    ) == (14, "days", "Fine", "approved")
    by_code = {r["code"]: r for r in listed["items"]}
    assert by_code[internal["code"]]["milestone"] is None  # the hidden milestone stays hidden
    assert listed["counts"] == {
        "total": 2,
        "pending": 1,
        "in_review": 0,
        "approved": 1,
        "declined": 0,
    }
    assert [(c["code"], c["status"]) for c in detail["change_requests"]] == [
        ("CR-02", "pending"),
        ("CR-01", "approved"),
    ]


async def test_client_cannot_reach_another_organisations_requests(
    client: httpx.AsyncClient, world: World
) -> None:
    listed = await call(
        client, world.contact, "GET", f"/client/projects/{world.other.id}/change-requests"
    )
    raised = await call(
        client,
        world.contact,
        "POST",
        f"/client/projects/{world.other.id}/change-requests",
        {"title": "x", "description": "y"},
    )
    staff_cr = await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.other.id}/change-requests",
        {"title": "x", "description": "y"},
    )
    peek = await call(client, world.contact, "GET", f"{client_crs(world)}/{staff_cr['id']}")

    assert listed.status_code == 404
    assert raised.status_code == 404
    assert peek.status_code == 404


# --- client dashboard (handoff: KPIs, 14 days, PM, recent updates) ------------------------------


async def test_dashboard_kpis_upcoming_window_pm_and_events(
    client: httpx.AsyncClient, world: World
) -> None:
    w = world
    base = f"/projects/{w.project.id}/milestones"
    await ok(
        client,
        w.pm,
        "POST",
        base,
        {"name": "Far away", "due_date": day(20), "client_visible": True},
    )
    await ok(
        client, w.pm, "POST", base, {"name": "Overdue", "due_date": day(-2), "client_visible": True}
    )
    report = await ok(
        client,
        w.pm,
        "POST",
        f"/projects/{w.project.id}/status-reports",
        {"rag": "green", "summary": "All good"},
    )
    await ok(
        client, w.pm, "POST", f"/projects/{w.project.id}/status-reports/{report['id']}/publish"
    )
    raised = await raise_move(client, w, 19)
    await review(client, w, raised["id"])
    w.other.status = "completed"

    portal = await ok(client, w.contact, "GET", "/client/portal")
    detail = await ok(client, w.contact, "GET", f"/client/projects/{w.project.id}")

    assert portal["kpis"] == {
        "active_projects": 1,
        "awaiting_input": 0,
        "upcoming_milestones": 1,
        "shared_reports": 1,
    }
    assert [m["name"] for m in portal["upcoming_milestones"]] == ["Delivery review"]
    assert portal["latest_report"]["id"] == report["id"]
    assert portal["latest_report"]["project_name"] == w.project.name
    assert portal["projects"][0]["project_manager"] == {"name": w.pm.name, "email": w.pm.email}
    events = [(e["kind"], e["status"]) for e in portal["updates"]]
    assert events == [
        ("change_request", "in_review"),
        ("change_request", "pending"),
        ("report", None),
        # The three shared milestones ("Milestone schedule published"), created before.
        ("milestone", "shared"),
        ("milestone", "shared"),
        ("milestone", "shared"),
    ]
    assert portal["updates"][0]["title"] == "CR-01 Extend delivery review"
    assert [(e["kind"], e["status"]) for e in detail["activity"]] == events


# --- conversation: comments and attachments (handoff "Request details") -------------------------


async def test_shared_comments_and_internal_notes(client: httpx.AsyncClient, world: World) -> None:
    raised = await raise_move(client, world, 19)
    staff = f"{crs(world)}/{raised['id']}/comments"
    portal = f"{client_crs(world)}/{raised['id']}/comments"

    await ok(client, world.contact, "POST", portal, {"body": "Can we get 3 more days?"})
    await ok(client, world.pm, "POST", staff, {"body": "Looking into it"})
    await ok(client, world.am, "POST", staff, {"body": "Budget is tight", "internal": True})
    sneaky = await call(client, world.contact, "POST", portal, {"body": "x", "internal": True})
    blank = await call(client, world.contact, "POST", portal, {"body": "   "})

    team_view = await ok(client, world.pm, "GET", staff)
    client_view = await ok(client, world.contact, "GET", portal)

    assert [(c["body"], c["internal"], c["author_is_client"]) for c in team_view] == [
        ("Can we get 3 more days?", False, True),
        ("Looking into it", False, False),
        ("Budget is tight", True, False),
    ]
    assert [(c["body"], c["from_client"]) for c in client_view] == [
        ("Can we get 3 more days?", True),
        ("Looking into it", False),
    ]
    assert set(client_view[0]) == {"id", "body", "author", "from_client", "created_at"}
    assert sneaky.status_code == 422  # clients cannot write internal notes
    assert blank.status_code == 422


async def test_attachments_up_and_down(client: httpx.AsyncClient, world: World) -> None:
    raised = await raise_move(client, world, 19)
    portal = f"{client_crs(world)}/{raised['id']}/attachments"
    staff = f"{crs(world)}/{raised['id']}/attachments"
    headers = {HEADER: str(world.contact.id)}

    uploaded = await client.post(
        API + portal,
        headers=headers,
        files={"file": ("brief.pdf", b"%PDF-1.4 hi", "application/pdf")},
    )
    refused = await client.post(
        API + portal,
        headers=headers,
        files={"file": ("run.exe", b"MZ", "application/octet-stream")},
    )
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["id"]

    listed = await ok(client, world.pm, "GET", staff)
    team_download = await client.get(
        f"{API}{staff}/{file_id}/download", headers={HEADER: str(world.pm.id)}
    )
    client_download = await client.get(f"{API}{portal}/{file_id}/download", headers=headers)

    assert refused.status_code == 415
    assert [(a["name"], a["uploaded_by"]["id"]) for a in listed] == [
        ("brief.pdf", str(world.contact.id))
    ]
    assert team_download.content == client_download.content == b"%PDF-1.4 hi"
    assert "attachment" in client_download.headers["content-disposition"]


async def test_conversation_stays_inside_the_clients_organisation(
    client: httpx.AsyncClient, world: World
) -> None:
    foreign = await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.other.id}/change-requests",
        {"title": "x", "description": "y"},
    )
    base = f"/client/projects/{world.other.id}/change-requests/{foreign['id']}"
    mine_path_foreign_id = f"{client_crs(world)}/{foreign['id']}/comments"

    comments = await call(client, world.contact, "GET", f"{base}/comments")
    files = await call(client, world.contact, "GET", f"{base}/attachments")
    cross = await call(client, world.contact, "GET", mine_path_foreign_id)
    dev = await call(
        client,
        world.dev,
        "GET",
        f"/projects/{world.other.id}/change-requests/{foreign['id']}/comments",
    )

    assert comments.status_code == files.status_code == 404
    assert cross.status_code == 404  # a request of another project, through the own project
    assert dev.status_code == 404


async def test_client_follows_every_status_and_the_decision(
    client: httpx.AsyncClient, world: World
) -> None:
    """Sheet row "Serve change requests updated versions to clients": the client sees each
    status the team sets, and the decision with its note and date."""
    raised = await raise_move(client, world, 19)
    path = f"{client_crs(world)}/{raised['id']}"

    async def seen() -> dict[str, Any]:
        result: dict[str, Any] = await ok(client, world.contact, "GET", path)
        return result

    assert (await seen())["status"] == "pending"
    await review(client, world, raised["id"])
    in_review = await seen()
    assert (in_review["status"], in_review["decided_at"]) == ("in_review", None)
    assert in_review["review_started_at"] is not None

    await decide(client, world, raised["id"], "declined", "Date is fixed by the launch")

    declined = await seen()
    assert declined["status"] == "declined"
    assert declined["decision_note"] == "Date is fixed by the launch"
    assert declined["decided_at"] is not None
    listed = await ok(client, world.contact, "GET", client_crs(world))
    assert listed["counts"]["declined"] == 1
    portal = await ok(client, world.contact, "GET", "/client/portal")
    assert (portal["updates"][0]["kind"], portal["updates"][0]["status"]) == (
        "change_request",
        "declined",
    )


async def test_impact_amount_and_unit_go_together(client: httpx.AsyncClient, world: World) -> None:
    raised = await raise_move(client, world, 19)
    path = f"{crs(world)}/{raised['id']}"

    alone = await call(client, world.pm, "PATCH", path, {"version": 1, "impact_effort_value": 3})
    bad_unit = await call(
        client,
        world.pm,
        "PATCH",
        path,
        {"version": 1, "impact_effort_value": 3, "impact_effort_unit": "months"},
    )
    set_both = await ok(
        client,
        world.pm,
        "PATCH",
        path,
        {"version": 1, "impact_effort_value": 3, "impact_effort_unit": "days"},
    )
    unit_only = await ok(
        client, world.pm, "PATCH", path, {"version": 2, "impact_effort_unit": "weeks"}
    )
    clear_one = await call(
        client, world.pm, "PATCH", path, {"version": 3, "impact_effort_value": None}
    )
    cleared = await ok(
        client,
        world.pm,
        "PATCH",
        path,
        {"version": 3, "impact_effort_value": None, "impact_effort_unit": None},
    )

    assert alone.status_code == 422
    assert alone.json()["error"]["details"][0]["issue"] == "pair_required"
    assert bad_unit.status_code == 422
    assert (set_both["impact_effort_value"], set_both["impact_effort_unit"]) == (3, "days")
    assert (unit_only["impact_effort_value"], unit_only["impact_effort_unit"]) == (3, "weeks")
    assert clear_one.status_code == 422
    assert (cleared["impact_effort_value"], cleared["impact_effort_unit"]) == (None, None)
