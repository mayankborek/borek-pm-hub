"""Admin user fields (BB-10): job title, and client contacts in the admin user list."""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.core.config import get_settings
from app.organisations.models import Organisation
from app.users.models import User
from tests.test_admin_users import SETTINGS, URL, create, headers, make_admin
from tests.test_auth import build_app, client_for


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    application = build_app(session)
    application.dependency_overrides[get_settings] = lambda: SETTINGS
    async with client_for(application) as http:
        yield http


async def make_org(session: AsyncSession, name: str) -> Organisation:
    organisation = Organisation(name=name, type="client")
    session.add(organisation)
    await session.flush()
    return organisation


# --- job title ----------------------------------------------------------------------------------


async def test_job_title_is_saved_trimmed_on_create(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)

    created = await create(client, admin, job_title="  Backend Developer ")

    assert created["user"]["job_title"] == "Backend Developer"
    user = await session.get(User, created["user"]["id"])
    assert user is not None
    assert user.job_title == "Backend Developer"


async def test_job_title_is_optional(client: httpx.AsyncClient, session: AsyncSession) -> None:
    admin = await make_admin(session)

    created = await create(client, admin)
    blank = await create(client, admin, email="blank@test.example", job_title="   ")

    assert created["user"]["job_title"] is None
    assert blank["user"]["job_title"] is None


async def test_job_title_is_edited_cleared_and_audited(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    user_id = (await create(client, admin, job_title="Developer"))["user"]["id"]
    url = f"{URL}/{user_id}"

    changed = await client.patch(url, json={"job_title": "Lead"}, headers=headers(admin))
    kept = await client.patch(url, json={"name": "Renamed"}, headers=headers(admin))
    cleared = await client.patch(url, json={"job_title": None}, headers=headers(admin))
    await client.patch(url, json={"job_title": "Tester"}, headers=headers(admin))
    emptied = await client.patch(url, json={"job_title": ""}, headers=headers(admin))

    assert changed.json()["job_title"] == "Lead"
    assert kept.json()["job_title"] == "Lead"  # left out = unchanged
    assert cleared.json()["job_title"] is None
    assert emptied.json()["job_title"] is None
    event = await session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "user.updated", AuditEvent.entity_id == user_id)
        .order_by(AuditEvent.at)
        .limit(1)
    )
    assert event is not None
    assert event.before == {"job_title": "Developer"}
    assert event.after == {"job_title": "Lead"}


async def test_bad_job_titles_are_refused(client: httpx.AsyncClient, session: AsyncSession) -> None:
    admin = await make_admin(session)
    body = {"name": "X", "email": "x@test.example", "role": "developer"}

    for title in ("x" * 101, "two\nlines", 5):
        response = await client.post(URL, json={**body, "job_title": title}, headers=headers(admin))
        assert response.status_code == 422, title


async def test_client_contacts_get_a_job_title_too(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session, "Acme")

    response = await client.post(
        f"/api/v1/organisations/{organisation.id}/members",
        json={"name": "Jordan", "email": "jordan@acme.example", "job_title": "Product Owner"},
        headers=headers(admin),
    )

    assert response.status_code == 201, response.text
    assert response.json()["member"]["job_title"] == "Product Owner"


# --- client contacts in the user list -----------------------------------------------------------


async def test_user_list_shows_client_contacts_and_filters_by_organisation(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    acme = await make_org(session, "Acme")
    globex = await make_org(session, "Globex")
    for organisation, email in ((acme, "a@acme.example"), (globex, "g@globex.example")):
        added = await client.post(
            f"/api/v1/organisations/{organisation.id}/members",
            json={"name": "Contact", "email": email},
            headers=headers(admin),
        )
        assert added.status_code == 201
    await create(client, admin, email="dev@test.example")

    everyone = (await client.get(URL, headers=headers(admin))).json()
    clients = (await client.get(URL, params={"role": "client"}, headers=headers(admin))).json()
    of_acme = (
        await client.get(URL, params={"organisation_id": str(acme.id)}, headers=headers(admin))
    ).json()

    assert {u["email"] for u in everyone["items"]} >= {
        "a@acme.example",
        "g@globex.example",
        "dev@test.example",
    }
    assert {u["email"] for u in clients["items"]} == {"a@acme.example", "g@globex.example"}
    assert [u["email"] for u in of_acme["items"]] == ["a@acme.example"]
    assert of_acme["items"][0]["organisation"] == {"id": str(acme.id), "name": "Acme"}
    assert of_acme["total"] == 1


async def test_organisation_filter_must_be_an_id(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)

    response = await client.get(URL, params={"organisation_id": "acme"}, headers=headers(admin))

    assert response.status_code == 422
