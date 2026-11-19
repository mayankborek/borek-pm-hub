"""Project type, category and priority, and external onboarding on project create (BB-13)."""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.common.enums import GlobalRole
from app.organisations.models import Organisation
from app.projects.models import Project
from app.users.models import User, UserInvite
from tests.conftest import make_project, make_user
from tests.test_auth import HEADER, build_app, client_for

PROJECTS = "/api/v1/projects"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def as_user(user: User) -> dict[str, str]:
    return {HEADER: str(user.id)}


async def make_client_org(session: AsyncSession, name: str = "Acme") -> Organisation:
    organisation = Organisation(name=name, type="client")
    session.add(organisation)
    await session.flush()
    return organisation


async def create(client: httpx.AsyncClient, user: User, **body: object) -> httpx.Response:
    return await client.post(
        PROJECTS, json={"code": "NEW", "name": "New", **body}, headers=as_user(user)
    )


async def actions(session: AsyncSession) -> list[str]:
    return list(await session.scalars(select(AuditEvent.action).order_by(AuditEvent.at)))


# --- defaults and fields ------------------------------------------------------------------------


async def test_a_new_project_is_internal_medium_with_no_category(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)

    response = await create(client, pm)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["type"] == "internal"
    assert body["priority"] == "medium"
    assert body["category"] is None
    assert body["client_organisation"] is None
    assert body["client_contact"] is None


async def test_fields_are_saved_and_shown_everywhere(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    acme = await make_client_org(session)

    created = await create(
        client,
        pm,
        type="external",
        client_organisation_id=str(acme.id),
        category="  Web Development ",
        priority="high",
    )

    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    detail = (await client.get(f"{PROJECTS}/{project_id}", headers=as_user(pm))).json()
    listed = (await client.get(PROJECTS, headers=as_user(pm))).json()["items"][0]
    for shown in (created.json(), detail, listed):
        assert shown["type"] == "external"
        assert shown["category"] == "Web Development"
        assert shown["priority"] == "high"
        assert shown["client_organisation"] == {"id": str(acme.id), "name": "Acme"}


async def test_bad_values_are_refused(client: httpx.AsyncClient, session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)

    for body in (
        {"type": "partner"},
        {"priority": "urgent"},
        {"category": "x" * 101},
        {"category": "two\nlines"},
    ):
        assert (await create(client, pm, **body)).status_code == 422, body


# --- the client must match the type -------------------------------------------------------------


async def test_external_needs_exactly_one_client_and_internal_none(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    acme = await make_client_org(session)
    new_client = {"name": "Globex"}

    for body in (
        {"type": "external"},
        {"type": "external", "client_organisation_id": str(acme.id), "new_client": new_client},
        {"type": "internal", "client_organisation_id": str(acme.id)},
        {"client_organisation_id": str(acme.id)},  # type defaults to internal
        {"new_client": new_client},
    ):
        response = await create(client, pm, **body)
        assert response.status_code == 422, body
    assert await session.scalar(select(func.count(Project.id))) == 0


async def test_patch_keeps_client_and_type_together(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    acme = await make_client_org(session)
    project_id = (await create(client, pm)).json()["id"]
    url = f"{PROJECTS}/{project_id}"

    async def patch(**body: object) -> httpx.Response:
        version = (await client.get(url, headers=as_user(pm))).json()["version"]
        return await client.patch(url, json={"version": version, **body}, headers=as_user(pm))

    only_type = await patch(type="external")
    only_client = await patch(client_organisation_id=str(acme.id))
    both = await patch(type="external", client_organisation_id=str(acme.id))
    drop_client = await patch(client_organisation_id=None)
    back = await patch(type="internal", client_organisation_id=None)

    assert only_type.status_code == 422
    assert only_type.json()["error"]["details"][0]["issue"] == "client_must_match_type"
    assert only_client.status_code == 422
    assert both.status_code == 200, both.text
    assert both.json()["type"] == "external"
    assert drop_client.status_code == 422
    assert back.status_code == 200
    assert back.json()["type"] == "internal"
    assert back.json()["client_organisation"] is None
    audit = await session.scalars(
        select(AuditEvent).where(AuditEvent.action == "project.type_changed")
    )
    assert [(e.before, e.after) for e in audit] == [
        ({"type": "internal"}, {"type": "external"}),
        ({"type": "external"}, {"type": "internal"}),
    ]


async def test_patch_changes_category_and_priority(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project_id = (await create(client, pm, category="Software")).json()["id"]
    url = f"{PROJECTS}/{project_id}"

    async def patch(**body: object) -> httpx.Response:
        version = (await client.get(url, headers=as_user(pm))).json()["version"]
        return await client.patch(url, json={"version": version, **body}, headers=as_user(pm))

    changed = await patch(priority="lowest", category="Data")
    kept = await patch(name="Renamed")
    cleared = await patch(category="")
    no_priority = await patch(priority=None)
    no_type = await patch(type=None)

    assert changed.json()["priority"] == "lowest"
    assert changed.json()["category"] == "Data"
    assert kept.json()["category"] == "Data"
    assert cleared.json()["category"] is None
    assert no_priority.status_code == 422
    assert no_type.status_code == 422


async def test_the_database_refuses_a_client_that_does_not_match_the_type(
    session: AsyncSession,
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    project.client_organisation_id = (await make_client_org(session)).id  # still internal

    with pytest.raises(IntegrityError):
        await session.flush()


# --- external onboarding ------------------------------------------------------------------------


async def test_external_project_with_a_new_client_and_contact_in_one_step(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)

    response = await create(
        client,
        pm,
        type="external",
        new_client={
            "name": " Globex ",
            "contact": {"name": "Jordan Lee", "email": "Jordan@Globex.Example"},
        },
    )

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["client_organisation"]["name"] == "Globex"
    organisation = await session.get(Organisation, body["client_organisation"]["id"])
    assert organisation is not None
    assert organisation.type == "client"
    contact = body["client_contact"]
    assert contact["member"]["email"] == "jordan@globex.example"
    assert contact["member"]["role"] == "client"
    assert contact["member"]["status"] == "invited"
    assert "#token=" in contact["invite"]["url"]
    person = await session.get(User, contact["member"]["id"])
    assert person is not None
    assert person.organisation_id == organisation.id
    assert await actions(session) == [
        "organisation.created",
        "organisation.member_added",
        "project.created",
    ]


async def test_new_client_without_a_contact(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    manager = await make_user(session, GlobalRole.MANAGER)

    response = await create(client, manager, type="external", new_client={"name": "Initech"})

    assert response.status_code == 201, response.text
    assert response.json()["client_organisation"]["name"] == "Initech"
    assert response.json()["client_contact"] is None


@pytest.mark.parametrize(
    ("new_client", "taken", "code"),
    [
        ({"name": "acme"}, "org", "DUPLICATE_ORGANISATION"),
        ({"name": "Fresh", "contact": {"name": "X", "email": "taken@x.example"}}, "email", None),
        ({"name": "Fresh"}, "code", "DUPLICATE_CODE"),
    ],
)
async def test_a_failure_saves_nothing(
    client: httpx.AsyncClient,
    session: AsyncSession,
    new_client: dict[str, object],
    taken: str,
    code: str | None,
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    await make_client_org(session, "Acme")
    await make_user(session, email="taken@x.example")
    if taken == "code":
        await make_project(session, pm.id, "NEW")
    await session.commit()
    before = {
        "orgs": await session.scalar(select(func.count(Organisation.id))),
        "users": await session.scalar(select(func.count(User.id))),
        "invites": await session.scalar(select(func.count(UserInvite.id))),
        "projects": await session.scalar(select(func.count(Project.id))),
        "audit": await session.scalar(select(func.count(AuditEvent.id))),
    }

    response = await create(client, pm, type="external", new_client=new_client)

    assert response.status_code == 409, response.text
    if code:
        assert response.json()["error"]["code"] == code
    else:
        assert response.json()["error"]["code"] == "EMAIL_TAKEN"
    # The app's request session ends without a commit, which undoes everything; the test
    # shares its session with the app, so do the same here.
    await session.rollback()
    after = {
        "orgs": await session.scalar(select(func.count(Organisation.id))),
        "users": await session.scalar(select(func.count(User.id))),
        "invites": await session.scalar(select(func.count(UserInvite.id))),
        "projects": await session.scalar(select(func.count(Project.id))),
        "audit": await session.scalar(select(func.count(AuditEvent.id))),
    }
    assert after == before


async def test_bad_new_client_input_is_refused(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)

    for new_client in (
        {"name": "  "},
        {"name": "X", "contact": {"name": "Y", "email": "nope"}},
        {"name": "X", "extra": 1},
    ):
        response = await create(client, pm, type="external", new_client=new_client)
        assert response.status_code == 422, new_client


async def test_developers_cannot_onboard(client: httpx.AsyncClient, session: AsyncSession) -> None:
    dev = await make_user(session, GlobalRole.DEVELOPER)

    response = await create(client, dev, type="external", new_client={"name": "Sneaky"})

    assert response.status_code == 403
    assert await session.scalar(select(func.count(Organisation.id))) == 0


# --- filters and category suggestions -----------------------------------------------------------


async def test_project_list_filters_by_type_priority_and_category(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    manager = await make_user(session, GlobalRole.MANAGER)
    acme = await make_client_org(session)
    for code, body in (
        ("INT", {"priority": "high", "category": "Software"}),
        ("EXT", {"type": "external", "client_organisation_id": str(acme.id), "category": "Web"}),
        ("LOW", {"priority": "low", "category": "software"}),
    ):
        assert (await create(client, manager, code=code, **body)).status_code == 201

    async def codes(**params: str) -> list[str]:
        response = await client.get(PROJECTS, params=params, headers=as_user(manager))
        assert response.status_code == 200, response.text
        return [p["code"] for p in response.json()["items"]]

    assert await codes(type="external") == ["EXT"]
    assert await codes(type="internal") == ["INT", "LOW"]
    assert await codes(priority="high") == ["INT"]
    assert await codes(category="SOFTWARE") == ["INT", "LOW"]
    assert (
        await client.get(PROJECTS, params={"type": "x"}, headers=as_user(manager))
    ).status_code == 422


async def test_category_suggestions_count_active_projects_and_search(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    for code, category in (
        ("A1", "Software"),
        ("A2", "Software"),
        ("A3", "software"),
        ("B1", "Web Development"),
        ("C1", None),
        ("OLD", "Archived only"),
    ):
        assert (await create(client, pm, code=code, category=category)).status_code == 201
    old = await session.scalar(select(Project).where(Project.code == "OLD"))
    assert old is not None
    await client.delete(f"{PROJECTS}/{old.id}", headers=as_user(pm))
    url = f"{PROJECTS}/categories"

    everything = (await client.get(url, headers=as_user(pm))).json()
    searched = (await client.get(url, params={"q": "web"}, headers=as_user(pm))).json()
    limited = (await client.get(url, params={"limit": 1}, headers=as_user(pm))).json()

    assert everything == [
        {"name": "Software", "project_count": 3},
        {"name": "Web Development", "project_count": 1},
    ]
    assert searched == [{"name": "Web Development", "project_count": 1}]
    assert len(limited) == 1


async def test_category_suggestions_are_for_project_creators(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    dev = await make_user(session, GlobalRole.DEVELOPER)

    response = await client.get(f"{PROJECTS}/categories", headers=as_user(dev))

    assert response.status_code == 403
