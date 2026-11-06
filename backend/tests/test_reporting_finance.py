"""BE-4 and the Account Manager's money: status reports, stakeholders, finance, portfolio RAG. Also
the fixes from the 06.11 audit: importer, assignee eligibility, last lead, role list."""

from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.common.enums import GlobalRole
from app.organisations.models import Organisation, OrganisationAccountManager
from app.projects.models import Project, ProjectMember
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for

P = "/api/v1/projects"
TODAY = date.today().isoformat()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def as_user(user: User) -> dict[str, str]:
    return {HEADER: str(user.id)}


async def events(session: AsyncSession, action: str) -> list[AuditEvent]:
    return list(await session.scalars(select(AuditEvent).where(AuditEvent.action == action)))


class World:
    admin: User
    manager: User
    pm: User
    pm_member: User
    pm_out: User
    dev: User
    am: User
    other_am: User
    org: Organisation
    project: Project
    url: str


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.admin = await make_user(session, GlobalRole.ADMIN)
    w.manager = await make_user(session, GlobalRole.MANAGER)
    w.pm = await make_user(session, GlobalRole.PM)
    w.pm_member = await make_user(session, GlobalRole.PM)
    w.pm_out = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session)
    w.am = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    w.other_am = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    w.org = Organisation(name="Acme", type="client")
    session.add(w.org)
    await session.flush()
    session.add(OrganisationAccountManager(organisation_id=w.org.id, user_id=w.am.id))
    w.project = await make_project(session, w.pm.id, "RPT")
    w.project.client_organisation_id = w.org.id
    for person in (w.pm_member, w.dev):
        session.add(
            ProjectMember(project_id=w.project.id, user_id=person.id, project_role="developer")
        )
    await session.flush()
    await session.refresh(w.project)
    w.url = f"{P}/{w.project.id}"
    return w


REPORT = {"rag": "amber", "summary": "Waiting for the client.", "risks": "Credentials late"}


# --- status reports -----------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["pm", "manager", "am"])
async def test_lead_manager_and_account_manager_write_and_publish(
    client: httpx.AsyncClient, session: AsyncSession, world: World, who: str
) -> None:
    author = getattr(world, who)
    base = f"{world.url}/status-reports"

    created = await client.post(base, headers=as_user(author), json=REPORT)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["state"] == "draft" and body["published_at"] is None
    assert body["report_date"] == TODAY
    assert body["author"]["id"] == str(author.id)

    url = f"{base}/{body['id']}"
    edited = await client.patch(
        url, headers=as_user(author), json={"version": body["version"], "rag": "red"}
    )
    assert edited.status_code == 200 and edited.json()["rag"] == "red"

    published = await client.post(f"{url}/publish", headers=as_user(author))
    assert published.status_code == 200
    assert published.json()["state"] == "published"
    assert published.json()["published_by"]["id"] == str(author.id)
    assert len(await events(session, "status_report.published")) == 1


async def test_a_draft_is_hidden_from_people_who_only_read(
    client: httpx.AsyncClient, world: World
) -> None:
    base = f"{world.url}/status-reports"
    draft = (await client.post(base, headers=as_user(world.pm), json=REPORT)).json()
    url = f"{base}/{draft['id']}"

    for reader in (world.dev, world.pm_member):
        listed = await client.get(base, headers=as_user(reader))
        assert listed.status_code == 200 and listed.json()["total"] == 0
        by_state = await client.get(base, headers=as_user(reader), params={"state": "draft"})
        assert by_state.json()["total"] == 0  # asking for drafts does not reveal them
        assert (await client.get(url, headers=as_user(reader))).status_code == 404

    await client.post(f"{url}/publish", headers=as_user(world.pm))
    assert (await client.get(base, headers=as_user(world.dev))).json()["total"] == 1
    assert (await client.get(url, headers=as_user(world.dev))).status_code == 200


async def test_a_published_report_cannot_change(client: httpx.AsyncClient, world: World) -> None:
    headers, base = as_user(world.pm), f"{world.url}/status-reports"
    report = (await client.post(base, headers=headers, json=REPORT)).json()
    url = f"{base}/{report['id']}"
    published = (await client.post(f"{url}/publish", headers=headers)).json()

    for response in (
        await client.patch(
            url, headers=headers, json={"version": published["version"], "rag": "red"}
        ),
        await client.post(f"{url}/publish", headers=headers),
        await client.delete(url, headers=headers),
    ):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "REPORT_PUBLISHED"


async def test_a_draft_can_be_removed_and_a_stale_edit_is_refused(
    client: httpx.AsyncClient, world: World
) -> None:
    headers, base = as_user(world.pm), f"{world.url}/status-reports"
    report = (await client.post(base, headers=headers, json=REPORT)).json()
    url = f"{base}/{report['id']}"
    stale = await client.patch(url, headers=headers, json={"version": 99, "rag": "red"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert (await client.delete(url, headers=headers)).status_code == 204
    assert (await client.get(url, headers=headers)).status_code == 404
    assert (await client.get(base, headers=headers)).json()["total"] == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"rag": "purple", "summary": "x"},
        {"rag": "green"},
        {"rag": "green", "summary": "   "},
        {"rag": "green", "summary": "x", "report_date": "1999-01-01"},
        {"rag": "green", "summary": "x", "surprise": 1},
    ],
)
async def test_invalid_reports_are_refused(
    client: httpx.AsyncClient, world: World, bad: dict[str, object]
) -> None:
    response = await client.post(f"{world.url}/status-reports", headers=as_user(world.pm), json=bad)
    assert response.status_code == 422


async def test_reports_cannot_be_reached_through_another_project(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    other = await make_project(session, world.pm.id, "OTH")
    report = (
        await client.post(f"{world.url}/status-reports", headers=as_user(world.pm), json=REPORT)
    ).json()
    response = await client.get(
        f"{P}/{other.id}/status-reports/{report['id']}", headers=as_user(world.pm)
    )
    assert response.status_code == 404


async def test_a_cancelled_project_takes_no_new_reports(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.project.status = "cancelled"
    await session.flush()
    response = await client.post(
        f"{world.url}/status-reports", headers=as_user(world.pm), json=REPORT
    )
    assert response.status_code == 409


# --- stakeholders -------------------------------------------------------------------------------


async def test_stakeholder_lifecycle_without_contact_details_in_the_log(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    base, headers = f"{world.url}/stakeholders", as_user(world.am)
    created = await client.post(
        base,
        headers=headers,
        json={
            "name": " Sam Sponsor ",
            "organisation": "Acme",
            "role_title": "Sponsor",
            "email": "Sam@Acme.Example",
            "phone": "+49 30 123456",
            "influence": "high",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Sam Sponsor" and body["email"] == "sam@acme.example"
    url = f"{base}/{body['id']}"

    edited = await client.patch(
        url, headers=headers, json={"version": body["version"], "phone": None, "influence": "low"}
    )
    assert edited.status_code == 200
    assert edited.json()["phone"] is None and edited.json()["influence"] == "low"
    stale = await client.patch(url, headers=headers, json={"version": 99, "notes": "x"})
    assert stale.status_code == 409

    assert (await client.delete(url, headers=headers)).status_code == 204
    assert (await client.get(base, headers=headers)).json() == []
    log = await session.scalars(select(AuditEvent))
    text = " ".join(f"{e.before} {e.after}" for e in log)
    assert "sam@acme.example" not in text and "+49" not in text


async def test_changing_contact_details_keeps_them_out_of_the_log(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    base, headers = f"{world.url}/stakeholders", as_user(world.am)
    created = (await client.post(base, headers=headers, json={"name": "Sam"})).json()
    edited = await client.patch(
        f"{base}/{created['id']}",
        headers=headers,
        json={"version": created["version"], "email": "new@acme.example", "phone": "+49 30 999"},
    )
    assert edited.status_code == 200
    update = (await events(session, "stakeholder.updated"))[0]
    assert update.after == {"changed": ["email", "phone"]}


@pytest.mark.parametrize(
    "bad", [{"name": ""}, {"name": "x", "phone": "call me"}, {"name": "x", "email": "nope"}]
)
async def test_invalid_stakeholders_are_refused(
    client: httpx.AsyncClient, world: World, bad: dict[str, object]
) -> None:
    response = await client.post(f"{world.url}/stakeholders", headers=as_user(world.pm), json=bad)
    assert response.status_code == 422


async def test_contact_details_are_not_for_plain_members(
    client: httpx.AsyncClient, world: World
) -> None:
    base = f"{world.url}/stakeholders"
    assert (await client.get(base, headers=as_user(world.dev))).status_code == 403
    assert (await client.get(base, headers=as_user(world.pm_member))).status_code == 403
    assert (await client.get(base, headers=as_user(world.pm_out))).status_code == 404
    assert (await client.get(base, headers=as_user(world.other_am))).status_code == 404


# --- money --------------------------------------------------------------------------------------


async def test_budget_entries_and_totals(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    base, headers = f"{world.url}/finance", as_user(world.am)

    empty = (await client.get(base, headers=headers)).json()
    assert empty["budget"] is None and empty["version"] == 0 and empty["remaining"] is None

    no_budget = await client.post(
        f"{base}/entries",
        headers=headers,
        json={"kind": "spend", "amount": "10", "entry_date": TODAY, "description": "x"},
    )
    assert no_budget.status_code == 409 and no_budget.json()["error"]["code"] == "NO_BUDGET"

    budget = await client.put(
        f"{base}/budget", headers=headers, json={"version": 0, "amount": "1000.00"}
    )
    assert budget.status_code == 200, budget.text
    assert budget.json()["currency"] == "EUR" and budget.json()["version"] == 1

    async def entry(kind: str, amount: str) -> str:
        response = await client.post(
            f"{base}/entries",
            headers=headers,
            json={"kind": kind, "amount": amount, "entry_date": TODAY, "description": "x"},
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    await entry("payment", "400.00")
    spend = await entry("spend", "250.50")
    wrong = await entry("spend", "9000.00")

    over = (await client.get(base, headers=headers)).json()
    assert Decimal(over["spent"]) == Decimal("9250.50") and over["over_budget"] is True
    assert Decimal(over["remaining"]) == Decimal("-8250.50")

    assert (await client.delete(f"{base}/entries/{wrong}", headers=headers)).status_code == 204
    fine = (await client.get(base, headers=headers)).json()
    assert Decimal(fine["received"]) == Decimal("400.00")
    assert Decimal(fine["spent"]) == Decimal("250.50")
    assert Decimal(fine["remaining"]) == Decimal("749.50")
    assert Decimal(fine["balance"]) == Decimal("149.50")
    assert fine["spent_percent"] == 25 and fine["over_budget"] is False

    listed = (await client.get(f"{base}/entries", headers=headers)).json()
    assert listed["total"] == 2 and spend in [e["id"] for e in listed["items"]]
    assert (await client.delete(f"{base}/entries/{wrong}", headers=headers)).status_code == 404

    assert [e.after for e in await events(session, "finance.budget_set")] == [
        {"amount": "1000.00", "currency": "EUR"}
    ]
    assert len(await events(session, "finance.entry_added")) == 3
    assert len(await events(session, "finance.entry_archived")) == 1


async def test_budget_uses_optimistic_locking_and_locks_the_currency(
    client: httpx.AsyncClient, world: World
) -> None:
    base, headers = f"{world.url}/finance", as_user(world.manager)
    await client.put(f"{base}/budget", headers=headers, json={"version": 0, "amount": "10"})

    stale = await client.put(f"{base}/budget", headers=headers, json={"version": 0, "amount": "20"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"

    usd = await client.put(
        f"{base}/budget", headers=headers, json={"version": 1, "amount": "10", "currency": "usd"}
    )
    assert usd.status_code == 200 and usd.json()["currency"] == "USD"

    await client.post(
        f"{base}/entries",
        headers=headers,
        json={"kind": "spend", "amount": "1", "entry_date": TODAY, "description": "x"},
    )
    locked = await client.put(
        f"{base}/budget", headers=headers, json={"version": 2, "amount": "10", "currency": "EUR"}
    )
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "CURRENCY_LOCKED"


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "spend", "amount": "0", "entry_date": TODAY, "description": "x"},
        {"kind": "spend", "amount": "-5", "entry_date": TODAY, "description": "x"},
        {"kind": "spend", "amount": "1.234", "entry_date": TODAY, "description": "x"},
        {"kind": "gift", "amount": "1", "entry_date": TODAY, "description": "x"},
        {"kind": "spend", "amount": "1", "entry_date": "1999-01-01", "description": "x"},
        {"kind": "spend", "amount": "1", "entry_date": TODAY, "description": "   "},
    ],
)
async def test_invalid_entries_are_refused(
    client: httpx.AsyncClient, world: World, bad: dict[str, object]
) -> None:
    response = await client.post(
        f"{world.url}/finance/entries", headers=as_user(world.manager), json=bad
    )
    assert response.status_code == 422


async def test_money_is_only_for_the_manager_and_the_clients_account_manager(
    client: httpx.AsyncClient, world: World
) -> None:
    base = f"{world.url}/finance"
    body = {"version": 0, "amount": "10"}
    for person, code in (
        (world.pm, 403),
        (world.pm_member, 403),
        (world.dev, 403),
        (world.pm_out, 404),
        (world.other_am, 404),
        (world.admin, 404),
    ):
        assert (await client.get(base, headers=as_user(person))).status_code == code
        assert (await client.get(f"{base}/entries", headers=as_user(person))).status_code == code
        assert (
            await client.put(f"{base}/budget", headers=as_user(person), json=body)
        ).status_code == code
    assert (await client.get(base, headers=as_user(world.manager))).status_code == 200
    assert (await client.get(base, headers=as_user(world.am))).status_code == 200


async def test_money_never_appears_in_project_responses(
    client: httpx.AsyncClient, world: World
) -> None:
    await client.put(
        f"{world.url}/finance/budget",
        headers=as_user(world.manager),
        json={"version": 0, "amount": "1234.56"},
    )
    for url in (world.url, P, f"{world.url}/tasks", "/api/v1/dashboard"):
        response = await client.get(url, headers=as_user(world.pm))
        assert response.status_code == 200
        assert "1234.56" not in response.text and "budget" not in response.text


# --- portfolio ----------------------------------------------------------------------------------


async def test_portfolio_shows_current_rag_and_money(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    other = await make_project(session, world.pm.id, "OTH")
    await session.refresh(other)
    base, headers = f"{world.url}/status-reports", as_user(world.manager)

    async def publish(rag: str, day: date) -> None:
        report = await client.post(
            base,
            headers=headers,
            json={"rag": rag, "summary": "s", "report_date": day.isoformat()},
        )
        await client.post(f"{base}/{report.json()['id']}/publish", headers=headers)

    await publish("green", date.today() - timedelta(days=7))
    await publish("red", date.today())
    await publish("amber", date.today() - timedelta(days=3))  # older date: does not win
    await client.post(base, headers=headers, json={"rag": "green", "summary": "unpublished"})
    await client.put(
        f"{world.url}/finance/budget", headers=headers, json={"version": 0, "amount": "100"}
    )

    body = (await client.get("/api/v1/portfolio", headers=headers)).json()
    items = {p["code"]: p for p in body["items"]}
    assert items["RPT"]["rag"] == "red"
    assert items["RPT"]["rag_date"] == TODAY
    assert Decimal(items["RPT"]["finance"]["budget"]) == Decimal("100")
    assert items["OTH"]["rag"] is None and items["OTH"]["finance"] is None
    assert body["by_rag"] == {"red": 1, "none": 1}

    red = await client.get("/api/v1/portfolio", headers=headers, params={"rag": "red"})
    assert [p["code"] for p in red.json()["items"]] == ["RPT"]
    green = await client.get("/api/v1/portfolio", headers=headers, params={"rag": "green"})
    assert green.json()["items"] == []


# --- fixes from the audit -----------------------------------------------------------------------


async def test_importer_does_not_add_people_who_do_no_project_work(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    for person, name in ((world.admin, "Ada Admin"), (world.am, "Ana Account")):
        person.name = name
    world.dev.name = "Dan Dev"
    await session.flush()
    csv = "Issue key;Summary;Assignee\nX-1;One;Ada Admin\nX-2;Two;Ana Account\nX-3;Three;Dan Dev\n"
    response = await client.post(
        f"{world.url}/tasks/import",
        headers=as_user(world.pm),
        params={"dry_run": "false"},
        files={"file": ("t.csv", csv.encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 3
    assert response.json()["members_added"] == []
    assert sorted(response.json()["unknown_assignees"]) == ["Ada Admin", "Ana Account"]
    members = set(
        await session.scalars(
            select(ProjectMember.user_id).where(ProjectMember.project_id == world.project.id)
        )
    )
    assert world.admin.id not in members and world.am.id not in members


async def test_a_member_whose_role_changed_cannot_be_assigned_tasks(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.project, world.pm.id)
    world.dev.global_role = GlobalRole.ADMIN.value  # was a member, then became administrator
    await session.flush()
    response = await client.put(
        f"/api/v1/tasks/{task.id}/assignee",
        headers=as_user(world.pm),
        json={"version": task.version, "assignee_id": str(world.dev.id)},
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["issue"] == "unknown_user"


@pytest.mark.parametrize("change", ["inactive", "role"])
async def test_a_lead_who_cannot_act_does_not_count_for_the_last_lead_rule(
    client: httpx.AsyncClient, session: AsyncSession, world: World, change: str
) -> None:
    session.add(
        ProjectMember(
            project_id=world.project.id, user_id=world.pm_out.id, project_role="project_lead"
        )
    )
    if change == "inactive":
        world.pm_out.is_active = False
    else:
        world.pm_out.global_role = GlobalRole.ADMIN.value
    await session.flush()
    response = await client.delete(
        f"{world.url}/members/{world.pm.id}", headers=as_user(world.manager)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LAST_PROJECT_LEAD"


async def test_admin_sees_every_role_with_counts(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.dev.is_active = False
    await session.flush()
    response = await client.get("/api/v1/admin/roles", headers=as_user(world.admin))
    assert response.status_code == 200
    roles = {r["id"]: r for r in response.json()}
    assert set(roles) == {r.value for r in GlobalRole}
    assert roles["pm"]["name"] == "Project Manager"
    assert (roles["pm"]["users"], roles["pm"]["active_users"]) == (3, 3)
    assert (roles["developer"]["users"], roles["developer"]["active_users"]) == (1, 0)
    assert roles["client"]["users"] == 0 and roles["client"]["assignable"] is False
    assert roles["manager"]["assignable"] is True
    for person in (world.manager, world.pm):
        assert (await client.get("/api/v1/admin/roles", headers=as_user(person))).status_code == 403


async def test_creating_a_user_returns_a_link_to_copy(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await client.post(
        "/api/v1/admin/users",
        headers=as_user(world.admin),
        json={"name": "Copy Link", "email": "copy@test.example", "role": "account_manager"},
    )
    assert response.status_code == 201
    invite = response.json()["invite"]
    assert "/set-password#token=" in invite["url"] and invite["expires_at"]
