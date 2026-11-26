"""Administrator handoff (24.11.2026): organisation setup in one call, details, named client
contacts per project, and the person access matrix for the administrator."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.core.config import get_settings
from app.organisations.models import Organisation
from app.projects.models import Project, ProjectClientContact
from app.users.models import User
from tests.conftest import make_project, make_user
from tests.test_admin_users import SETTINGS, headers, make_admin
from tests.test_auth import build_app, client_for

ORGS = "/api/v1/organisations"
ACCESS = "/api/v1/access-overview"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    application = build_app(session)
    application.dependency_overrides[get_settings] = lambda: SETTINGS
    async with client_for(application) as http:
        yield http


async def setup_body(session: AsyncSession, **changes: object) -> dict:
    am = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    pm = await make_user(session, GlobalRole.PM)
    return {
        "name": "Cedar Labs",
        "industry": "Biotech",
        "website": "cedarlabs.example",
        "primary_contact_email": "Hello@CedarLabs.Example",
        "account_manager_ids": [str(am.id)],
        "project_manager_id": str(pm.id),
        "contacts": [
            {"name": "Rae Park", "email": "rae@cedarlabs.example", "job_title": "CTO"},
            {"name": "Sam Ode", "email": "sam@cedarlabs.example"},
        ],
        **changes,
    }


async def test_admin_sets_up_a_client_in_one_call(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    body = await setup_body(session)
    response = await client.post(ORGS, json=body, headers=headers(admin))
    assert response.status_code == 201, response.text
    org = response.json()
    assert org["industry"] == "Biotech"
    assert org["website"] == "https://cedarlabs.example"
    assert org["primary_contact_email"] == "hello@cedarlabs.example"
    assert [m["id"] for m in org["account_managers"]] == body["account_manager_ids"]
    assert org["project_manager"]["id"] == body["project_manager_id"]
    assert org["projects"] == []  # "No project yet"
    assert org["contact_count"] == 2
    created = org["contacts_created"]
    assert [c["member"]["email"] for c in created] == [
        "rae@cedarlabs.example",
        "sam@cedarlabs.example",
    ]
    assert all(c["invite"]["url"].startswith("https://hub.example/") for c in created)
    assert response.headers["Cache-Control"] == "no-store"

    # read back: same details, no invite links
    again = await client.get(f"{ORGS}/{org['id']}", headers=headers(admin))
    assert again.json()["website"] == "https://cedarlabs.example"
    assert "contacts_created" not in again.json()


async def test_setup_is_all_or_nothing_and_validates_fields(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    taken = await make_user(session, email="rae@cedarlabs.example")
    developer = await make_user(session)
    cases = [
        ({"website": "not a site"}, 422),
        ({"primary_contact_email": "nope"}, 422),
        ({"project_manager_id": str(developer.id)}, 422),
        (
            {
                "contacts": [
                    {"name": "A", "email": "x@y.example"},
                    {"name": "B", "email": "x@y.example"},
                ]
            },
            422,
        ),
        ({}, 409),  # the first contact's email is already an account: nothing is saved
    ]
    for changes, status in cases:
        body = await setup_body(session, **changes)
        response = await client.post(ORGS, json=body, headers=headers(admin))
        assert response.status_code == status, (changes, response.text)
    assert await session.scalar(select(func.count(Organisation.id))) == 0
    assert taken.organisation_id is None


async def test_admin_edits_details_and_account_managers_in_one_save(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    body = await setup_body(session, contacts=[])
    org = (await client.post(ORGS, json=body, headers=headers(admin))).json()
    other_am = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    url = f"{ORGS}/{org['id']}"

    changed = await client.patch(
        url,
        json={
            "version": org["version"],
            "industry": "",
            "website": None,
            "project_manager_id": None,
            "account_manager_ids": [str(other_am.id)],
        },
        headers=headers(admin),
    )
    assert changed.status_code == 200, changed.text
    out = changed.json()
    assert out["name"] == "Cedar Labs"
    assert out["industry"] is None and out["website"] is None
    assert out["project_manager"] is None
    assert [m["id"] for m in out["account_managers"]] == [str(other_am.id)]
    assert out["version"] > org["version"]

    # only the Account Managers change: still a saved change with a new version
    again = await client.patch(
        url,
        json={"version": out["version"], "account_manager_ids": []},
        headers=headers(admin),
    )
    assert again.status_code == 200
    assert again.json()["account_managers"] == []
    assert again.json()["version"] > out["version"]
    stale = await client.patch(
        url, json={"version": org["version"], "name": "X"}, headers=headers(admin)
    )
    assert stale.status_code == 409
    empty_name = await client.patch(
        url, json={"version": again.json()["version"], "name": None}, headers=headers(admin)
    )
    assert empty_name.status_code == 422


async def client_with_project(
    client: httpx.AsyncClient, session: AsyncSession, admin: User
) -> tuple[dict, Project, list[str]]:
    org = (await client.post(ORGS, json=await setup_body(session), headers=headers(admin))).json()
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, "CDR")
    project.client_organisation_id = uuid.UUID(org["id"])
    project.project_type = "external"
    await session.flush()
    contact_ids = [c["member"]["id"] for c in org["contacts_created"]]
    return org, project, contact_ids


async def test_projects_show_named_contacts_and_need_one(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    org, project, contact_ids = await client_with_project(client, session, admin)
    listed = await client.get(ORGS, headers=headers(admin), params={"type": "client"})
    row = next(o for o in listed.json()["items"] if o["id"] == org["id"])
    assert row["projects"] == [
        {
            "id": str(project.id),
            "code": "CDR",
            "name": "Test project",
            "contacts": [],
            "needs_contact": True,
        }
    ]

    url = f"{ORGS}/{org['id']}/projects/{project.id}/contacts"
    set_ = await client.put(url, json={"user_ids": contact_ids}, headers=headers(admin))
    assert set_.status_code == 200, set_.text
    assert {c["id"] for c in set_.json()["contacts"]} == set(contact_ids)
    assert set_.json()["needs_contact"] is False

    stranger = await make_user(session, GlobalRole.CLIENT)  # not this organisation's contact
    for body, status in (
        ({"user_ids": []}, 422),
        ({"user_ids": [str(stranger.id)]}, 422),
    ):
        response = await client.put(url, json=body, headers=headers(admin))
        assert response.status_code == status, body
    other = await make_project(session, admin.id, "OTH")
    wrong = await client.put(
        f"{ORGS}/{org['id']}/projects/{other.id}/contacts",
        json={"user_ids": contact_ids},
        headers=headers(admin),
    )
    assert wrong.status_code == 404
    pm = await make_user(session, GlobalRole.PM)
    assert (
        await client.put(url, json={"user_ids": contact_ids}, headers=headers(pm))
    ).status_code == 403


async def test_last_named_contact_cannot_be_removed(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    org, project, (rae, sam) = await client_with_project(client, session, admin)
    url = f"{ORGS}/{org['id']}/projects/{project.id}/contacts"
    assert (
        await client.put(url, json={"user_ids": [rae]}, headers=headers(admin))
    ).status_code == 200

    blocked = await client.delete(f"{ORGS}/{org['id']}/members/{rae}", headers=headers(admin))
    assert blocked.status_code == 409
    error = blocked.json()["error"]
    assert error["code"] == "LAST_PROJECT_CONTACT"
    assert error["message"] == "Assign another contact to Test project before removing Rae Park."
    assert error["details"][0]["message"] == str(project.id)
    # Sam is not a named contact anywhere: removing them is fine
    sam_out = await client.delete(f"{ORGS}/{org['id']}/members/{sam}", headers=headers(admin))
    assert sam_out.status_code == 200

    # with another active contact named, Rae can go
    newcomer = await client.post(
        f"{ORGS}/{org['id']}/members",
        json={"name": "Lee Moss", "email": "lee@cedarlabs.example"},
        headers=headers(admin),
    )
    lee = newcomer.json()["member"]["id"]
    await client.put(url, json={"user_ids": [rae, lee]}, headers=headers(admin))
    removed = await client.delete(f"{ORGS}/{org['id']}/members/{rae}", headers=headers(admin))
    assert removed.status_code == 200


async def test_onboarded_contact_becomes_the_projects_named_contact(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    response = await client.post(
        "/api/v1/projects",
        json={
            "code": "NEW",
            "name": "New",
            "type": "external",
            "new_client": {"name": "Globex", "contact": {"name": "Jo", "email": "jo@g.example"}},
        },
        headers=headers(pm),
    )
    assert response.status_code == 201, response.text
    contact_id = response.json()["client_contact"]["member"]["id"]
    named = list(await session.scalars(select(ProjectClientContact.user_id)))
    assert [str(i) for i in named] == [contact_id]


async def test_admin_reads_and_exports_person_access(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    org, project, (rae, _sam) = await client_with_project(client, session, admin)
    await client.put(
        f"{ORGS}/{org['id']}/projects/{project.id}/contacts",
        json={"user_ids": [rae]},
        headers=headers(admin),
    )
    lead = (
        await session.scalars(select(User).where(User.global_role == GlobalRole.PM.value))
    ).all()

    everyone = (await client.get(ACCESS, headers=headers(admin))).json()
    roles = {p["role"] for p in everyone["items"]}
    assert {"client", "account_manager", "pm"} <= roles
    rae_row = next(p for p in everyone["items"] if p["id"] == rae)
    assert [(p["project_code"], p["source"]) for p in rae_row["projects"]] == [
        ("CDR", "client_contact")
    ]

    picked = await client.get(
        ACCESS,
        headers=headers(admin),
        params=[("person_id", rae), ("person_id", str(lead[0].id))],
    )
    assert {p["id"] for p in picked.json()["items"]} == {rae, str(lead[0].id)}
    by_project = await client.get(
        ACCESS, headers=headers(admin), params=[("project_id", str(project.id))]
    )
    assert rae in {p["id"] for p in by_project.json()["items"]}

    pdf = await client.get(f"{ACCESS}/export", headers=headers(admin), params={"format": "pdf"})
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    csv = await client.get(f"{ACCESS}/export", headers=headers(admin))
    assert "Rae Park" in csv.content.decode("utf-8-sig")


async def test_user_search_matches_the_organisation_name(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """Users directory: "Search name, email or organisation" (Administrator handoff)."""
    admin = await make_admin(session)
    org = (await client.post(ORGS, json=await setup_body(session), headers=headers(admin))).json()
    found = await client.get("/api/v1/admin/users", params={"q": "cedar"}, headers=headers(admin))
    assert found.status_code == 200
    emails = {u["email"] for u in found.json()["items"]}
    assert emails == {"rae@cedarlabs.example", "sam@cedarlabs.example"}
    assert all(u["organisation"]["id"] == org["id"] for u in found.json()["items"])
