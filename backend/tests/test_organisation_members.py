"""Client organisation members (/organisations/{id}/members) and the invite lookup
(/auth/invite-info). Runs in AUTH_MODE=local with real bearer tokens, like the live system."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.common.enums import GlobalRole
from app.core.config import get_settings
from app.organisations.models import Organisation
from app.users.models import User, UserInvite
from tests.conftest import make_user
from tests.test_admin_users import (
    PASSWORD,
    SETTINGS,
    accept,
    headers,
    login,
    make_admin,
    token_of,
)
from tests.test_auth import build_app, client_for

INFO = "/api/v1/auth/invite-info"


def members_url(organisation: Organisation) -> str:
    return f"/api/v1/organisations/{organisation.id}/members"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    application = build_app(session)
    application.dependency_overrides[get_settings] = lambda: SETTINGS
    async with client_for(application) as http:
        yield http


async def make_org(session: AsyncSession, name: str = "Acme", kind: str = "client") -> Organisation:
    organisation = Organisation(name=name, type=kind)
    session.add(organisation)
    await session.flush()
    return organisation


async def add(
    client: httpx.AsyncClient,
    admin: User,
    organisation: Organisation,
    email: str = "jordan@acme.example",
) -> dict:
    response = await client.post(
        members_url(organisation),
        json={"name": "Jordan Lee", "email": email},
        headers=headers(admin),
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- adding -------------------------------------------------------------------------------------


async def test_adding_a_member_creates_a_client_account_with_an_invite_link(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session)

    response = await client.post(
        members_url(organisation),
        json={"name": "  Jordan Lee ", "email": " Jordan@Acme.Example "},
        headers=headers(admin),
    )

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    member = body["member"]
    assert member["name"] == "Jordan Lee"
    assert member["email"] == "jordan@acme.example"
    assert member["role"] == "client"
    assert member["status"] == "invited"
    assert member["password_set"] is False
    assert member["invite_pending"] is True
    assert body["invite"]["url"].startswith("https://hub.example/set-password#token=")
    user = await session.get(User, member["id"])
    assert user is not None
    assert user.organisation_id == organisation.id
    assert user.global_role == GlobalRole.CLIENT.value
    events = (
        await session.scalars(
            select(AuditEvent).where(AuditEvent.action == "organisation.member_added")
        )
    ).all()
    assert len(events) == 1
    assert events[0].entity_id == organisation.id
    assert events[0].after == {
        "user_id": member["id"],
        "name": "Jordan Lee",
        "email": "jordan@acme.example",
    }
    assert token_of(body) not in str(events[0].after)


async def test_the_member_sets_a_password_with_the_link_and_signs_in(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session)
    created = await add(client, admin, organisation)

    assert (await accept(client, token_of(created))).status_code == 200
    assert (await login(client, "jordan@acme.example", PASSWORD)).status_code == 200

    listed = (await client.get(members_url(organisation), headers=headers(admin))).json()
    assert [m["status"] for m in listed["items"]] == ["active"]


async def test_a_taken_email_is_refused_whatever_the_case(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session)
    await make_user(session, email="taken@acme.example")

    response = await client.post(
        members_url(organisation),
        json={"name": "Again", "email": "TAKEN@acme.example"},
        headers=headers(admin),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_internal_and_archived_organisations_get_no_members(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    internal = await make_org(session, "Borek", kind="internal")
    archived = await make_org(session, "Gone")
    archived.archived_at = datetime.now(UTC)
    await session.flush()
    body = {"name": "X", "email": "x@acme.example"}

    to_internal = await client.post(members_url(internal), json=body, headers=headers(admin))
    to_archived = await client.post(members_url(archived), json=body, headers=headers(admin))
    list_internal = await client.get(members_url(internal), headers=headers(admin))

    assert to_internal.status_code == 409
    assert to_internal.json()["error"]["code"] == "NOT_A_CLIENT_ORGANISATION"
    assert list_internal.status_code == 409
    assert to_archived.status_code == 409
    assert to_archived.json()["error"]["code"] == "ORGANISATION_ARCHIVED"
    assert (await client.get(members_url(archived), headers=headers(admin))).status_code == 200


async def test_unknown_organisation_is_404(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)

    response = await client.get(
        "/api/v1/organisations/00000000-0000-0000-0000-000000000000/members",
        headers=headers(admin),
    )

    assert response.status_code == 404


async def test_invalid_input_is_422(client: httpx.AsyncClient, session: AsyncSession) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session)

    for body in (
        {"name": "X", "email": "not-an-email"},
        {"name": "   ", "email": "a@acme.example"},
        {"name": "X", "email": "a@acme.example", "role": "admin"},
    ):
        response = await client.post(members_url(organisation), json=body, headers=headers(admin))
        assert response.status_code == 422, body


async def test_only_administrators_manage_members(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    organisation = await make_org(session)
    for role in (GlobalRole.MANAGER, GlobalRole.ACCOUNT_MANAGER, GlobalRole.PM):
        other = await make_user(session, role)
        listed = await client.get(members_url(organisation), headers=headers(other))
        added = await client.post(
            members_url(organisation),
            json={"name": "X", "email": f"{role.value}@acme.example"},
            headers=headers(other),
        )
        assert listed.status_code == 403, role
        assert added.status_code == 403, role
    assert (await client.get(members_url(organisation))).status_code == 401


# --- listing ------------------------------------------------------------------------------------


async def test_list_shows_only_this_organisations_people_with_their_status(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session)
    other = await make_org(session, "Globex")
    first = await add(client, admin, organisation, "a@acme.example")
    expired = await add(client, admin, organisation, "b@acme.example")
    await add(client, admin, other, "c@globex.example")
    removed = await add(client, admin, organisation, "d@acme.example")
    invite = await session.scalar(
        select(UserInvite).where(UserInvite.user_id == expired["member"]["id"])
    )
    assert invite is not None
    invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.flush()
    url = f"{members_url(organisation)}/{removed['member']['id']}"
    assert (await client.delete(url, headers=headers(admin))).status_code == 200

    response = await client.get(members_url(organisation), headers=headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    by_email = {m["email"]: m["status"] for m in body["items"]}
    assert by_email == {
        "a@acme.example": "invited",
        "b@acme.example": "invite_expired",
        "d@acme.example": "deactivated",
    }
    assert body["items"][-1]["email"] == "d@acme.example"  # deactivated people last
    assert first["member"]["id"] in {m["id"] for m in body["items"]}


# --- new link -----------------------------------------------------------------------------------


async def test_a_new_link_replaces_the_old_one(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session)
    created = await add(client, admin, organisation)
    url = f"{members_url(organisation)}/{created['member']['id']}/invite"

    response = await client.post(url, headers=headers(admin))

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    renewed = response.json()
    assert renewed["member"]["status"] == "invited"
    assert (await accept(client, token_of(created))).status_code == 400
    assert (await accept(client, token_of(renewed))).status_code == 200


async def test_a_new_link_is_refused_for_people_of_another_organisation(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session)
    other = await make_org(session, "Globex")
    created = await add(client, admin, other)
    internal_person = await make_user(session, GlobalRole.DEVELOPER)

    for user_id in (created["member"]["id"], internal_person.id):
        url = f"{members_url(organisation)}/{user_id}/invite"
        response = await client.post(url, headers=headers(admin))
        assert response.status_code == 404


async def test_a_removed_member_gets_no_new_link(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session)
    created = await add(client, admin, organisation)
    member_url = f"{members_url(organisation)}/{created['member']['id']}"
    await client.delete(member_url, headers=headers(admin))

    response = await client.post(f"{member_url}/invite", headers=headers(admin))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USER_INACTIVE"


# --- removing -----------------------------------------------------------------------------------


async def test_removing_deactivates_the_account_and_ends_sign_in(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session)
    created = await add(client, admin, organisation)
    await accept(client, token_of(created))
    member_url = f"{members_url(organisation)}/{created['member']['id']}"

    response = await client.delete(member_url, headers=headers(admin))
    again = await client.delete(member_url, headers=headers(admin))

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "deactivated"
    assert again.status_code == 200
    user = await session.get(User, created["member"]["id"])
    assert user is not None
    await session.refresh(user)
    assert user.is_active is False
    assert user.organisation_id == organisation.id  # kept, nothing deleted
    assert (await login(client, "jordan@acme.example", PASSWORD)).status_code == 401
    removed_events = (
        await session.scalars(
            select(AuditEvent).where(AuditEvent.action == "organisation.member_removed")
        )
    ).all()
    assert len(removed_events) == 1  # removing twice logs once


async def test_only_client_contacts_can_be_removed_here(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session)
    manager = await make_user(session, GlobalRole.ACCOUNT_MANAGER)
    manager.organisation_id = organisation.id
    await session.flush()

    response = await client.delete(
        f"{members_url(organisation)}/{manager.id}", headers=headers(admin)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_A_CLIENT_CONTACT"
    await session.refresh(manager)
    assert manager.is_active is True


# --- invite lookup ------------------------------------------------------------------------------


async def test_invite_info_tells_who_the_link_is_for_without_using_it(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    admin.name = "Rina Admin"
    organisation = await make_org(session)
    created = await add(client, admin, organisation)

    response = await client.post(INFO, json={"token": token_of(created)})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "jordan@acme.example"
    assert body["name"] == "Jordan Lee"
    assert body["role"] == "client"
    assert body["role_label"] == "Client"
    assert body["organisation_name"] == "Acme"
    assert body["inviter_name"] == "Rina Admin"
    assert body["expires_at"] == created["invite"]["expires_at"]
    assert response.headers["cache-control"] == "no-store"
    assert (await accept(client, token_of(created))).status_code == 200  # still usable


async def test_invite_info_refuses_every_bad_link_the_same_way(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    organisation = await make_org(session)
    used = await add(client, admin, organisation, "used@acme.example")
    await accept(client, token_of(used))
    replaced = await add(client, admin, organisation, "old@acme.example")
    await client.post(
        f"{members_url(organisation)}/{replaced['member']['id']}/invite", headers=headers(admin)
    )
    inactive = await add(client, admin, organisation, "off@acme.example")
    await client.delete(
        f"{members_url(organisation)}/{inactive['member']['id']}", headers=headers(admin)
    )

    for token in (token_of(used), token_of(replaced), token_of(inactive), "x" * 43):
        response = await client.post(INFO, json={"token": token})
        assert response.status_code == 400, token
        assert response.json()["error"]["code"] == "INVALID_INVITE"


async def test_invite_info_for_internal_people_has_no_organisation(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    created = await client.post(
        "/api/v1/admin/users",
        json={"name": "Dev", "email": "dev@borek.example", "role": "developer"},
        headers=headers(admin),
    )

    body = (await client.post(INFO, json={"token": token_of(created.json())})).json()

    assert body["role_label"] == "Developer"
    assert body["organisation_name"] is None


async def test_invite_info_needs_a_plausible_token(client: httpx.AsyncClient) -> None:
    for body in ({}, {"token": "short"}, {"token": "x" * 201}, {"token": "x" * 30, "a": 1}):
        assert (await client.post(INFO, json=body)).status_code == 422, body
