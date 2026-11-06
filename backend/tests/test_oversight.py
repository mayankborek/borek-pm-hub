"""Sprint 02-26: audit log, organisations, Account Manager access, portfolio, access overview."""

from collections.abc import AsyncIterator
from datetime import date, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.common.enums import GlobalRole
from app.organisations.models import Organisation, OrganisationAccountManager
from app.projects.models import Project, ProjectMember
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for

ORGS = "/api/v1/organisations"
PROJECTS = "/api/v1/projects"
AUDIT = "/api/v1/admin/audit-events"
PORTFOLIO = "/api/v1/portfolio"
ACCESS = "/api/v1/access-overview"


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
    dev: User
    am: User
    other_am: User
    client_org: Organisation
    other_org: Organisation
    served: Project  # for client_org, assigned to `am`
    unserved: Project  # for other_org
    internal: Project  # no client


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.admin = await make_user(session, GlobalRole.ADMIN)
    w.manager = await make_user(session, GlobalRole.MANAGER)
    w.pm = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session)
    w.am = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    w.other_am = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    w.client_org = Organisation(name="Acme", type="client")
    w.other_org = Organisation(name="Globex", type="client")
    session.add_all([w.client_org, w.other_org])
    await session.flush()
    session.add(OrganisationAccountManager(organisation_id=w.client_org.id, user_id=w.am.id))
    w.served = await make_project(session, w.pm.id, "SRV")
    w.unserved = await make_project(session, w.pm.id, "UNS")
    w.internal = await make_project(session, w.pm.id, "INT")
    w.served.client_organisation_id = w.client_org.id
    w.unserved.client_organisation_id = w.other_org.id
    await session.flush()
    for project in (w.served, w.unserved, w.internal):
        await session.refresh(project)
    return w


# --- audit log ----------------------------------------------------------------------------------


async def test_each_member_change_writes_exactly_one_event(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    base, headers = f"{PROJECTS}/{world.served.id}/members", as_user(world.pm)

    await client.post(base, headers=headers, json={"user_id": str(world.dev.id)})
    await client.patch(
        f"{base}/{world.dev.id}", headers=headers, json={"project_role": "project_lead"}
    )
    await client.patch(
        f"{base}/{world.dev.id}", headers=headers, json={"project_role": "project_lead"}
    )  # no change, no event
    await client.delete(f"{base}/{world.dev.id}", headers=headers)

    added = await events(session, "member.added")
    changed = await events(session, "member.role_changed")
    removed = await events(session, "member.removed")
    assert [len(added), len(changed), len(removed)] == [1, 1, 1]
    assert added[0].actor_id == world.pm.id
    assert added[0].entity_id == world.dev.id
    assert added[0].project_id == world.served.id
    assert added[0].after == {"project_role": "developer"}
    assert changed[0].before == {"project_role": "developer"}
    assert changed[0].after == {"project_role": "project_lead"}
    assert removed[0].before == {"project_role": "project_lead"}


async def test_a_refused_change_writes_no_event(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    response = await client.delete(
        f"{PROJECTS}/{world.served.id}/members/{world.pm.id}", headers=as_user(world.pm)
    )
    assert response.status_code == 409
    await session.rollback()
    assert await events(session, "member.removed") == []


async def test_project_create_and_archive_are_recorded(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    created = await client.post(
        PROJECTS, headers=as_user(world.pm), json={"code": "NEW", "name": "New"}
    )
    project_id = created.json()["id"]
    await client.delete(f"{PROJECTS}/{project_id}", headers=as_user(world.pm))
    assert [str(e.entity_id) for e in await events(session, "project.created")] == [project_id]
    assert [str(e.entity_id) for e in await events(session, "project.archived")] == [project_id]


async def test_user_administration_is_recorded_without_secrets(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    headers = as_user(world.admin)
    created = await client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={"name": "New Person", "email": "new@test.example", "role": "manager"},
    )
    assert created.status_code == 201
    user_id = created.json()["user"]["id"]
    token = created.json()["invite"]["url"].split("#")[-1]
    url = f"/api/v1/admin/users/{user_id}"
    await client.patch(url, headers=headers, json={"name": "Renamed"})
    await client.post(f"{url}/invite", headers=headers)
    await client.post(f"{url}/deactivate", headers=headers)
    await client.post(f"{url}/activate", headers=headers)

    updated = await events(session, "user.updated")
    assert updated[0].before == {"name": "New Person"}
    assert updated[0].after == {"name": "Renamed"}
    for action in ("user.created", "user.invite_created", "user.deactivated", "user.activated"):
        assert len(await events(session, action)) == 1, action
    everything = await session.scalars(select(AuditEvent))
    assert token not in " ".join(f"{e.before} {e.after}" for e in everything)


@pytest.mark.parametrize(
    "statement", ["UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events"]
)
async def test_the_database_refuses_to_change_the_audit_log(
    session: AsyncSession, world: World, statement: str
) -> None:
    session.add(
        AuditEvent(action="test", entity_type="user", entity_id=world.pm.id, actor_id=world.pm.id)
    )
    await session.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        await session.execute(text(statement))


async def test_only_the_admin_reads_the_audit_log_with_filters(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    base = f"{PROJECTS}/{world.served.id}/members"
    await client.post(base, headers=as_user(world.pm), json={"user_id": str(world.dev.id)})
    await client.post(
        f"{PROJECTS}/{world.unserved.id}/members",
        headers=as_user(world.manager),
        json={"user_id": str(world.dev.id)},
    )

    for user in (world.manager, world.pm, world.dev, world.am):
        assert (await client.get(AUDIT, headers=as_user(user))).status_code == 403

    headers = as_user(world.admin)
    everything = (await client.get(AUDIT, headers=headers)).json()
    assert everything["total"] == 2
    assert everything["items"][0]["actor"]["id"] == str(world.manager.id)  # newest first
    by_project = await client.get(
        AUDIT, headers=headers, params={"project_id": str(world.served.id)}
    )
    assert [e["actor"]["id"] for e in by_project.json()["items"]] == [str(world.pm.id)]
    by_actor = await client.get(AUDIT, headers=headers, params={"actor_id": str(world.manager.id)})
    assert by_actor.json()["total"] == 1
    assert (await client.get(AUDIT, headers=headers, params={"action": "member.removed"})).json()[
        "total"
    ] == 0
    assert (await client.get(AUDIT, headers=headers, params={"to": "2000-01-01T00:00:00Z"})).json()[
        "total"
    ] == 0


# --- organisations ------------------------------------------------------------------------------


async def test_admin_creates_edits_and_archives_an_organisation(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    headers = as_user(world.admin)
    created = await client.post(ORGS, headers=headers, json={"name": "  Initech "})
    assert created.status_code == 201
    body = created.json()
    assert (body["name"], body["type"], body["account_managers"]) == ("Initech", "client", [])

    url = f"{ORGS}/{body['id']}"
    renamed = await client.patch(url, headers=headers, json={"version": 1, "name": "Initrode"})
    assert renamed.status_code == 200 and renamed.json()["version"] == 2
    stale = await client.patch(url, headers=headers, json={"version": 1, "name": "Other"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"

    assert (await client.delete(url, headers=headers)).status_code == 204
    assert (await client.delete(url, headers=headers)).status_code == 204  # harmless
    names = [o["name"] for o in (await client.get(ORGS, headers=headers)).json()["items"]]
    assert "Initrode" not in names
    archived = await client.get(ORGS, headers=headers, params={"include_archived": True})
    assert "Initrode" in [o["name"] for o in archived.json()["items"]]
    assert len(await events(session, "organisation.archived")) == 1


@pytest.mark.parametrize("name", ["acme", "ACME"])
async def test_organisation_names_are_unique_whatever_the_case(
    client: httpx.AsyncClient, world: World, name: str
) -> None:
    response = await client.post(ORGS, headers=as_user(world.admin), json={"name": name})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_ORGANISATION"


async def test_organisation_in_use_cannot_be_archived(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    response = await client.delete(f"{ORGS}/{world.client_org.id}", headers=as_user(world.admin))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ORGANISATION_IN_USE"


async def test_who_may_read_and_change_organisations(
    client: httpx.AsyncClient, world: World
) -> None:
    for user in (world.admin, world.manager, world.pm, world.am):
        assert (await client.get(ORGS, headers=as_user(user))).status_code == 200
    assert (await client.get(ORGS, headers=as_user(world.dev))).status_code == 403
    for user in (world.manager, world.pm, world.dev, world.am):
        response = await client.post(ORGS, headers=as_user(user), json={"name": "X"})
        assert response.status_code == 403
        response = await client.put(
            f"{ORGS}/{world.other_org.id}/account-managers",
            headers=as_user(user),
            json={"user_ids": []},
        )
        assert response.status_code == 403


async def test_a_project_gets_a_client_only_from_active_client_organisations(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    internal_org = Organisation(name="Borek", type="internal")
    session.add(internal_org)
    await session.flush()
    headers = as_user(world.pm)

    good = await client.post(
        PROJECTS,
        headers=headers,
        json={"code": "CLI", "name": "c", "client_organisation_id": str(world.client_org.id)},
    )
    assert good.status_code == 201
    assert good.json()["client_organisation"] == {"id": str(world.client_org.id), "name": "Acme"}

    bad = await client.post(
        PROJECTS,
        headers=headers,
        json={"code": "BAD", "name": "c", "client_organisation_id": str(internal_org.id)},
    )
    assert bad.status_code == 422

    url = f"{PROJECTS}/{world.internal.id}"
    changed = await client.patch(
        url,
        headers=headers,
        json={"version": world.internal.version, "client_organisation_id": str(world.other_org.id)},
    )
    assert changed.status_code == 200
    assert changed.json()["client_organisation"]["name"] == "Globex"
    audit = await events(session, "project.client_changed")
    assert audit[0].after == {"client_organisation_id": str(world.other_org.id)}
    await session.refresh(world.internal)
    cleared = await client.patch(
        url,
        headers=headers,
        json={"version": world.internal.version, "client_organisation_id": None},
    )
    assert cleared.status_code == 200 and cleared.json()["client_organisation"] is None


async def test_admin_sets_a_users_organisation(client: httpx.AsyncClient, world: World) -> None:
    headers = as_user(world.admin)
    created = await client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "name": "Org Person",
            "email": "org@test.example",
            "role": "developer",
            "organisation_id": str(world.other_org.id),
        },
    )
    assert created.json()["user"]["organisation"]["name"] == "Globex"
    url = f"/api/v1/admin/users/{created.json()['user']['id']}"
    moved = await client.patch(
        url, headers=headers, json={"organisation_id": str(world.client_org.id)}
    )
    assert moved.json()["organisation"]["name"] == "Acme"
    unknown = await client.patch(url, headers=headers, json={"organisation_id": str(world.dev.id)})
    assert unknown.status_code == 422


# --- account managers ---------------------------------------------------------------------------


async def test_admin_replaces_the_account_managers_of_a_client(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    url, headers = f"{ORGS}/{world.client_org.id}/account-managers", as_user(world.admin)
    response = await client.put(url, headers=headers, json={"user_ids": [str(world.other_am.id)]})
    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == [str(world.other_am.id)]
    org = (await client.get(f"{ORGS}/{world.client_org.id}", headers=headers)).json()
    assert [p["id"] for p in org["account_managers"]] == [str(world.other_am.id)]
    audit = await events(session, "organisation.account_managers_changed")
    assert audit[0].before == {"user_ids": [str(world.am.id)]}
    assert audit[0].after == {"user_ids": [str(world.other_am.id)]}

    same = await client.put(url, headers=headers, json={"user_ids": [str(world.other_am.id)]})
    assert same.status_code == 200
    assert len(await events(session, "organisation.account_managers_changed")) == 1

    # the first one lost access at once
    project = f"{PROJECTS}/{world.served.id}"
    assert (await client.get(project, headers=as_user(world.am))).status_code == 404
    assert (await client.get(project, headers=as_user(world.other_am))).status_code == 200


async def test_only_active_account_managers_can_be_assigned_and_only_to_clients(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    url, headers = f"{ORGS}/{world.client_org.id}/account-managers", as_user(world.admin)
    inactive = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    inactive.is_active = False
    await session.flush()
    for bad in (world.dev.id, world.pm.id, inactive.id):
        response = await client.put(url, headers=headers, json={"user_ids": [str(bad)]})
        assert response.status_code == 422

    internal_org = Organisation(name="Borek", type="internal")
    session.add(internal_org)
    await session.flush()
    response = await client.put(
        f"{ORGS}/{internal_org.id}/account-managers",
        headers=headers,
        json={"user_ids": [str(world.am.id)]},
    )
    assert response.status_code == 422


async def test_account_manager_reads_projects_of_their_clients_only(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.served, world.pm.id, title="Served")
    await make_task(session, world.unserved, world.pm.id, title="Unserved")
    await make_task(session, world.internal, world.pm.id, title="Internal")
    for project in (world.served, world.unserved, world.internal):
        await session.refresh(project)
    headers = as_user(world.am)

    codes = [p["code"] for p in (await client.get(PROJECTS, headers=headers)).json()["items"]]
    assert codes == ["SRV"]
    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()
    assert [t["title"] for t in tasks["items"]] == ["Served"]
    assert "Unserved" not in (await client.get("/api/v1/tasks/export", headers=headers)).text

    served = f"{PROJECTS}/{world.served.id}"
    assert (await client.get(served, headers=headers)).status_code == 200
    assert (await client.get(f"{served}/tasks", headers=headers)).status_code == 200
    assert (await client.get(f"{PROJECTS}/{world.unserved.id}", headers=headers)).status_code == 404
    assert (await client.get(f"{PROJECTS}/{world.internal.id}", headers=headers)).status_code == 404
    assert (
        await client.get(f"{PROJECTS}/{world.unserved.id}/tasks", headers=headers)
    ).status_code == 404


async def test_account_manager_cannot_change_anything_in_their_clients_projects(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    task = await make_task(session, world.served, world.pm.id)
    await session.refresh(world.served)
    headers = as_user(world.am)
    served = f"{PROJECTS}/{world.served.id}"
    for method, url, body in (
        ("PATCH", served, {"version": world.served.version, "name": "x"}),
        ("DELETE", served, None),
        ("POST", f"{served}/members", {"user_id": str(world.dev.id)}),
        ("POST", f"{served}/tasks", {"title": "x"}),
        ("POST", f"{served}/statuses", {"name": "x", "category": "todo"}),
        ("PATCH", f"/api/v1/tasks/{task.id}", {"version": 1, "title": "x"}),
        ("POST", f"/api/v1/tasks/{task.id}/comments", {"body": "x"}),
        ("DELETE", f"/api/v1/tasks/{task.id}", None),
    ):
        response = await client.request(method, url, headers=headers, json=body)
        assert response.status_code == 403, (method, url, response.text)


async def test_account_manager_has_no_dashboard_picker_or_my_work(
    client: httpx.AsyncClient, world: World
) -> None:
    headers = as_user(world.am)
    for url in ("/api/v1/dashboard", "/api/v1/dashboard/me", "/api/v1/users", "/api/v1/me/tasks"):
        assert (await client.get(url, headers=headers)).status_code == 403, url
    assert (await client.get(ACCESS, headers=headers)).status_code == 403


async def test_archived_projects_are_gone_for_the_account_manager(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    url = f"{PROJECTS}/{world.served.id}"
    assert (await client.delete(url, headers=as_user(world.pm))).status_code == 204
    await session.refresh(world.served)
    assert (await client.get(url, headers=as_user(world.am))).status_code == 404
    listed = await client.get(
        PROJECTS, headers=as_user(world.am), params={"include_archived": True}
    )
    assert listed.json()["items"] == []


# --- portfolio ----------------------------------------------------------------------------------


async def test_portfolio_for_manager_shows_all_active_projects_with_numbers(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    overdue = date.today() - timedelta(days=3)
    await make_task(session, world.served, world.pm.id, due_date=overdue)
    await make_task(session, world.served, world.pm.id, status="Done")
    await make_task(session, world.unserved, world.pm.id, status="Blocked")
    session.add(
        ProjectMember(project_id=world.served.id, user_id=world.dev.id, project_role="developer")
    )
    world.internal.status = "cancelled"
    await session.flush()

    response = await client.get(PORTFOLIO, headers=as_user(world.manager))

    assert response.status_code == 200
    body = response.json()
    assert [p["code"] for p in body["items"]] == ["INT", "SRV", "UNS"]
    assert body["total"] == 3
    assert body["by_status"] == {"cancelled": 1, "planned": 2}
    assert body["summary"]["total"] == 3
    served = body["items"][1]
    assert served["client_organisation"]["name"] == "Acme"
    assert [lead["id"] for lead in served["leads"]] == [str(world.pm.id)]
    assert served["member_count"] == 2
    assert served["tasks"]["overdue"] == 1
    assert served["tasks"]["completed"] == 1
    assert body["items"][0]["tasks"]["total"] == 0


async def test_portfolio_for_account_manager_is_limited_to_their_clients(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    await make_task(session, world.unserved, world.pm.id)
    body = (await client.get(PORTFOLIO, headers=as_user(world.am))).json()
    assert [p["code"] for p in body["items"]] == ["SRV"]
    assert body["summary"]["total"] == 0  # the task of another client is not counted

    other = await client.get(
        PORTFOLIO,
        headers=as_user(world.am),
        params={"client_organisation_id": str(world.other_org.id)},
    )
    assert other.json()["items"] == []  # asking for another client gives nothing


async def test_portfolio_filters_sorting_and_paging(
    client: httpx.AsyncClient, world: World
) -> None:
    headers = as_user(world.manager)
    by_client = await client.get(
        PORTFOLIO, headers=headers, params={"client_organisation_id": str(world.other_org.id)}
    )
    assert [p["code"] for p in by_client.json()["items"]] == ["UNS"]
    by_q = await client.get(PORTFOLIO, headers=headers, params={"q": "srv"})
    assert [p["code"] for p in by_q.json()["items"]] == ["SRV"]
    backwards = await client.get(PORTFOLIO, headers=headers, params={"sort": "-code"})
    assert [p["code"] for p in backwards.json()["items"]] == ["UNS", "SRV", "INT"]
    paged = await client.get(PORTFOLIO, headers=headers, params={"page": 2, "page_size": 2})
    assert [p["code"] for p in paged.json()["items"]] == ["UNS"]
    assert paged.json()["total"] == 3
    assert (await client.get(PORTFOLIO, headers=headers, params={"sort": "bad"})).status_code == 422


@pytest.mark.parametrize("attr", ["admin", "pm", "dev"])
async def test_other_roles_have_no_portfolio_or_access_overview(
    client: httpx.AsyncClient, world: World, attr: str
) -> None:
    headers = as_user(getattr(world, attr))
    assert (await client.get(PORTFOLIO, headers=headers)).status_code == 403
    assert (await client.get(ACCESS, headers=headers)).status_code == 403
    assert (await client.get(f"{ACCESS}/export", headers=headers)).status_code == 403


# --- access overview ----------------------------------------------------------------------------


async def test_access_overview_shows_people_projects_and_why(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    session.add(
        ProjectMember(project_id=world.served.id, user_id=world.dev.id, project_role="developer")
    )
    await session.flush()
    headers = as_user(world.manager)

    body = (await client.get(ACCESS, headers=headers)).json()
    people = {p["id"]: p for p in body["items"]}
    assert str(world.admin.id) not in people  # no project work
    assert [
        (a["project_code"], a["project_role"]) for a in people[str(world.pm.id)]["projects"]
    ] == [("INT", "project_lead"), ("SRV", "project_lead"), ("UNS", "project_lead")]
    assert [
        (a["project_code"], a["project_role"], a["source"])
        for a in people[str(world.am.id)]["projects"]
    ] == [("SRV", "account_manager", "client_assignment")]
    assert people[str(world.other_am.id)]["projects"] == []

    one = await client.get(ACCESS, headers=headers, params={"project_id": str(world.served.id)})
    assert {p["id"] for p in one.json()["items"]} == {
        str(world.pm.id),
        str(world.dev.id),
        str(world.am.id),
    }
    roles = await client.get(ACCESS, headers=headers, params={"role": "developer"})
    assert [p["id"] for p in roles.json()["items"]] == [str(world.dev.id)]


async def test_access_overview_export_is_a_safe_csv(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.dev.name = "=HYPERLINK(1)"
    session.add(
        ProjectMember(project_id=world.served.id, user_id=world.dev.id, project_role="developer")
    )
    await session.flush()
    response = await client.get(f"{ACCESS}/export", headers=as_user(world.manager))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    text_body = response.content.decode("utf-8-sig")
    assert text_body.splitlines()[0].startswith("Name;Email;Role;Active;Project key")
    assert "'=HYPERLINK(1);" in text_body
    assert ";SRV;" in text_body
