"""User administration (/admin/users) and invite links (/auth/accept-invite, /auth/change-password).

Everything runs in AUTH_MODE=local with real bearer tokens, like the live system.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.auth.security import create_access_token, hash_password, verify_password
from app.common.enums import GlobalRole
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.projects.models import ProjectMember
from app.users.models import User, UserInvite
from tests.conftest import make_project, make_user
from tests.test_auth import build_app, client_for

URL = "/api/v1/admin/users"
PASSWORD = "a long enough password"
SETTINGS = Settings(
    _env_file=None,
    auth_mode="local",
    environment="test",
    secret_key="k" * 40,
    frontend_url="https://hub.example/",
    max_failed_logins=3,
)


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    application = build_app(session)
    application.dependency_overrides[get_settings] = lambda: SETTINGS
    async with client_for(application) as http:
        yield http


def headers(user: User) -> dict[str, str]:
    token, _ = create_access_token(user.id, SETTINGS)
    return {"Authorization": f"Bearer {token}"}


async def make_admin(session: AsyncSession, email: str = "boss@test.example") -> User:
    return await make_user(session, GlobalRole.ADMIN, email=email)


async def create(client: httpx.AsyncClient, admin: User, **changes: object) -> dict:
    body = {"name": "New Person", "email": "new@test.example", "role": "developer", **changes}
    response = await client.post(URL, json=body, headers=headers(admin))
    assert response.status_code == 201, response.text
    return response.json()


def token_of(created: dict) -> str:
    return str(created["invite"]["url"]).split("#token=")[1]


async def accept(client: httpx.AsyncClient, token: str, password: str = PASSWORD) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/accept-invite", json={"token": token, "password": password}
    )


async def login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


# --- creating accounts and invite links ---------------------------------------------------------


async def test_admin_creates_an_account_and_gets_a_one_time_link(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)

    response = await client.post(
        URL,
        json={
            "name": "  Jaya Joshi ",
            "email": " Jaya.Joshi@Test.Example ",
            "role": "developer",
            "join_date": "2026-11-02",
        },
        headers=headers(admin),
    )

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    user = body["user"]
    assert user["name"] == "Jaya Joshi" and user["email"] == "jaya.joshi@test.example"
    assert user["role"] == "developer" and user["is_active"] is True
    assert user["join_date"] == "2026-11-02"
    assert user["password_set"] is False and user["invite_pending"] is True
    assert user["projects"] == []
    assert response.headers["location"] == f"{URL}/{user['id']}"
    token = token_of(body)
    assert body["invite"]["url"] == f"https://hub.example/set-password#token={token}"
    assert datetime.fromisoformat(body["invite"]["expires_at"]) > datetime.now(UTC) + timedelta(
        days=6
    )
    # The database holds no password and only a hash of the token.
    stored = await session.scalar(select(User).where(User.email == "jaya.joshi@test.example"))
    assert stored is not None and stored.password_hash is None
    hashes = (await session.scalars(select(UserInvite.token_hash))).all()
    assert len(hashes) == 1 and token not in hashes[0] and len(hashes[0]) == 64


async def test_person_sets_a_password_with_the_link_and_can_sign_in(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    created = await create(client, admin)
    email = created["user"]["email"]
    assert (await login(client, email, PASSWORD)).status_code == 401  # no password yet

    response = await accept(client, token_of(created))

    assert response.status_code == 200 and response.json() == {"email": email}
    signed_in = await login(client, email, PASSWORD)
    assert signed_in.status_code == 200
    assert signed_in.json()["user"]["role"] == "developer"
    listed = await client.get(f"{URL}/{created['user']['id']}", headers=headers(admin))
    assert listed.json()["password_set"] is True and listed.json()["invite_pending"] is False


async def test_a_link_works_only_once(client: httpx.AsyncClient, session: AsyncSession) -> None:
    admin = await make_admin(session)
    token = token_of(await create(client, admin))

    first = await accept(client, token)
    second = await accept(client, token, "another long password")

    assert first.status_code == 200
    assert second.status_code == 400 and second.json()["error"]["code"] == "INVALID_INVITE"


async def test_every_bad_link_gets_the_same_answer(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    h = headers(admin)
    expired = await create(client, admin, email="a@test.example")
    replaced = await create(client, admin, email="b@test.example")
    deactivated = await create(client, admin, email="c@test.example")
    row = await session.scalar(
        select(UserInvite).where(UserInvite.user_id == uuid.UUID(expired["user"]["id"]))
    )
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()
    newer = await client.post(f"{URL}/{replaced['user']['id']}/invite", headers=h)
    await client.post(f"{URL}/{deactivated['user']['id']}/deactivate", headers=h)

    responses = [
        await accept(client, token_of(expired)),  # expired
        await accept(client, token_of(replaced)),  # replaced by a newer link
        await accept(client, token_of(deactivated)),  # account switched off
        await accept(client, "x" * 43),  # never issued
    ]

    assert {r.status_code for r in responses} == {400}
    assert {r.json()["error"]["code"] for r in responses} == {"INVALID_INVITE"}
    assert len({r.json()["error"]["message"] for r in responses}) == 1
    assert (await accept(client, token_of(newer.json()))).status_code == 200  # the newer one works


async def test_the_password_rule_applies_to_the_link(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    token = token_of(await create(client, admin))

    short = await accept(client, token, "too short")
    too_long = await accept(client, token, "x" * 129)

    assert short.status_code == 422 and too_long.status_code == 422
    assert (await accept(client, token)).status_code == 200  # the link was not used up by errors


async def test_a_new_link_resets_a_forgotten_password(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    created = await create(client, admin)
    await accept(client, token_of(created))
    user = await session.get(User, created["user"]["id"])
    assert user is not None
    user.failed_login_count = 2
    await session.flush()

    reset = await client.post(f"{URL}/{user.id}/invite", headers=headers(admin))
    assert reset.status_code == 200 and reset.headers["cache-control"] == "no-store"
    assert reset.json()["user"]["invite_pending"] is True
    assert (await accept(client, token_of(reset.json()), "brand new password")).status_code == 200

    assert (await login(client, user.email, PASSWORD)).status_code == 401
    assert (await login(client, user.email, "brand new password")).status_code == 200


async def test_links_are_only_made_for_active_users(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    created = await create(client, admin)
    user_id = created["user"]["id"]
    await client.post(f"{URL}/{user_id}/deactivate", headers=headers(admin))

    response = await client.post(f"{URL}/{user_id}/invite", headers=headers(admin))

    assert response.status_code == 409 and response.json()["error"]["code"] == "USER_INACTIVE"


async def test_accepting_and_changing_passwords_exist_only_in_local_mode(
    session: AsyncSession,
) -> None:
    async with client_for(build_app(session, auth_mode="dev")) as dev_client:
        response = await accept(dev_client, "x" * 43)
        change = await dev_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "a", "new_password": PASSWORD},
        )
    assert response.status_code == 404
    assert change.status_code in (401, 404)


# --- validation ---------------------------------------------------------------------------------


async def test_duplicate_emails_are_refused_whatever_the_case(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    await create(client, admin, email="same@test.example")
    legacy = await make_user(session, GlobalRole.PM, email="Legacy@Test.Example")  # old mixed case

    again = await client.post(
        URL,
        json={"name": "X", "email": "SAME@test.example", "role": "pm"},
        headers=headers(admin),
    )
    clash = await client.post(
        URL,
        json={"name": "X", "email": "legacy@test.example", "role": "pm"},
        headers=headers(admin),
    )

    assert again.status_code == 409 and again.json()["error"]["code"] == "EMAIL_TAKEN"
    assert clash.status_code == 409
    assert legacy.email == "Legacy@Test.Example"  # untouched


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "not-an-email"},
        {"email": "a@b"},
        {"email": "a b@test.example"},
        {"email": "a@test..example"},
        {"email": "x" * 320 + "@test.example"},
        {"name": "   "},
        {"name": "bad\x00name"},
        {"role": "client"},  # exists, but the admin screens do not offer it yet
        {"role": "superuser"},
        {"join_date": "1999-12-31"},
        {"join_date": "2101-01-01"},
        {"surprise": "field"},
    ],
)
async def test_bad_input_is_refused(
    client: httpx.AsyncClient, session: AsyncSession, changes: dict[str, object]
) -> None:
    admin = await make_admin(session)
    body = {"name": "New Person", "email": "new@test.example", "role": "pm", **changes}

    response = await client.post(URL, json=body, headers=headers(admin))

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert await session.scalar(select(User).where(User.email == "new@test.example")) is None


# --- who may use it -----------------------------------------------------------------------------


@pytest.mark.parametrize("role", [GlobalRole.PM, GlobalRole.DEVELOPER, GlobalRole.CLIENT])
async def test_only_administrators_may_use_the_admin_api(
    client: httpx.AsyncClient, session: AsyncSession, role: GlobalRole
) -> None:
    other = await make_user(session, role)
    target = await make_user(session, GlobalRole.DEVELOPER)
    h = headers(other)

    calls = [
        client.get(URL, headers=h),
        client.post(URL, json={"name": "x", "email": "x@test.example", "role": "pm"}, headers=h),
        client.get(f"{URL}/{target.id}", headers=h),
        client.patch(f"{URL}/{target.id}", json={"name": "y"}, headers=h),
        client.post(f"{URL}/{target.id}/deactivate", headers=h),
        client.post(f"{URL}/{target.id}/activate", headers=h),
        client.post(f"{URL}/{target.id}/invite", headers=h),
    ]
    for call in calls:
        assert (await call).status_code == 403


async def test_admin_api_needs_a_token(client: httpx.AsyncClient) -> None:
    assert (await client.get(URL)).status_code == 401


async def test_administrator_sees_no_project_data(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    # even when a PM has added the administrator to a project
    project = await make_project(session, admin.id, code="SEC")
    session.add(ProjectMember(project_id=project.id, user_id=admin.id))
    await session.flush()
    h = headers(admin)
    assert (await client.get(f"/api/v1/projects/{project.id}", headers=h)).status_code == 403
    assert (await client.get(f"/api/v1/projects/{project.id}/tasks", headers=h)).status_code == 403

    assert (await client.get("/api/v1/projects", headers=h)).status_code == 403
    assert (await client.get("/api/v1/tasks", headers=h)).status_code == 403
    assert (await client.get("/api/v1/tasks/export", headers=h)).status_code == 403
    assert (await client.get("/api/v1/me/tasks", headers=h)).status_code == 403
    assert (await client.get("/api/v1/users", headers=h)).status_code == 403
    assert (await client.get("/api/v1/dashboard", headers=h)).status_code == 403
    assert (await client.get("/api/v1/auth/me", headers=h)).json()["role"] == "admin"


# --- listing ------------------------------------------------------------------------------------


async def test_list_shows_projects_counts_search_and_filters(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    alex = await make_user(session, GlobalRole.PM, email="alex@test.example")
    alex.name = "Alex Morgan"
    noah = await make_user(session, GlobalRole.DEVELOPER, email="noah@test.example")
    noah.name = "Noah Patel"
    gone = await make_user(session, GlobalRole.DEVELOPER, email="gone@test.example")
    gone.name = "Gone Away"
    gone.is_active = False
    site = await make_project(session, admin.id, code="WEB")
    portal = await make_project(session, admin.id, code="POR")
    old = await make_project(session, admin.id, code="OLD")
    old.archived_at = datetime.now(UTC)
    for project, user in ((site, alex), (portal, alex), (site, noah), (old, noah)):
        session.add(ProjectMember(project_id=project.id, user_id=user.id))
    await session.flush()
    h = headers(admin)

    everyone = (await client.get(URL, headers=h)).json()
    assert everyone["total"] == 4 and everyone["active_total"] == 3
    names = [u["name"] for u in everyone["items"]]
    assert names == sorted(names)
    by_name = {u["name"]: u for u in everyone["items"]}
    assert [p["code"] for p in by_name["Alex Morgan"]["projects"]] == ["POR", "WEB"]
    assert [p["code"] for p in by_name["Noah Patel"]["projects"]] == ["WEB"]  # archived left out
    assert set(by_name["Alex Morgan"]) == {
        "id", "name", "email", "role", "is_active", "join_date", "password_set",
        "invite_pending", "projects", "created_at", "organisation",
    }  # fmt: skip

    async def names_for(**params: str) -> list[str]:
        response = await client.get(URL, headers=h, params=params)
        assert response.status_code == 200, response.text
        return [u["name"] for u in response.json()["items"]]

    assert await names_for(q="NOAH") == ["Noah Patel"]
    assert await names_for(q="alex@test") == ["Alex Morgan"]
    assert await names_for(q="%") == []  # wildcards are literal
    assert await names_for(role="developer") == ["Gone Away", "Noah Patel"]
    assert await names_for(status="inactive") == ["Gone Away"]
    assert await names_for(status="active", role="developer") == ["Noah Patel"]
    inactive = (await client.get(URL, headers=h, params={"status": "inactive"})).json()
    assert inactive["total"] == 1 and inactive["active_total"] == 0
    assert (await client.get(URL, headers=h, params={"status": "weird"})).status_code == 422
    assert (await client.get(URL, headers=h, params={"role": "wizard"})).status_code == 422


async def test_list_pages(client: httpx.AsyncClient, session: AsyncSession) -> None:
    admin = await make_admin(session)
    for number in range(4):
        user = await make_user(session, GlobalRole.DEVELOPER)
        user.name = f"User {number}"
    await session.flush()

    page = (
        await client.get(URL, headers=headers(admin), params={"page": 2, "page_size": 2})
    ).json()

    assert page["total"] == 5 and page["page"] == 2 and len(page["items"]) == 2


async def test_invite_pending_goes_away_when_the_link_expires(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    created = await create(client, admin)
    invite = await session.scalar(select(UserInvite))
    assert invite is not None
    invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.flush()

    detail = await client.get(f"{URL}/{created['user']['id']}", headers=headers(admin))

    assert detail.json()["invite_pending"] is False and detail.json()["password_set"] is False


# --- editing ------------------------------------------------------------------------------------


async def test_admin_edits_name_email_role_and_join_date(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    created = await create(client, admin, join_date="2026-11-02")
    path = f"{URL}/{created['user']['id']}"
    h = headers(admin)

    renamed = await client.patch(
        path, json={"name": " Jaya J. ", "email": "JAYA@test.example", "role": "pm"}, headers=h
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Jaya J." and renamed.json()["email"] == "jaya@test.example"
    assert renamed.json()["role"] == "pm" and renamed.json()["join_date"] == "2026-11-02"

    cleared = await client.patch(path, json={"join_date": None}, headers=h)
    assert cleared.json()["join_date"] is None and cleared.json()["role"] == "pm"  # rest kept
    assert (await client.patch(path, json={}, headers=h)).status_code == 200  # nothing to change


@pytest.mark.parametrize("field", ["name", "email", "role"])
async def test_required_fields_cannot_be_cleared(
    client: httpx.AsyncClient, session: AsyncSession, field: str
) -> None:
    admin = await make_admin(session)
    target = await make_user(session, GlobalRole.DEVELOPER)

    response = await client.patch(f"{URL}/{target.id}", json={field: None}, headers=headers(admin))

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == field


async def test_edit_checks_duplicates_and_unknown_users(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    first = await make_user(session, GlobalRole.DEVELOPER, email="first@test.example")
    second = await make_user(session, GlobalRole.DEVELOPER, email="second@test.example")
    h = headers(admin)

    taken = await client.patch(
        f"{URL}/{second.id}", json={"email": "FIRST@test.example"}, headers=h
    )
    same = await client.patch(f"{URL}/{first.id}", json={"email": "First@test.example"}, headers=h)
    missing = await client.patch(
        f"{URL}/00000000-0000-4000-8000-0000000000ff", json={"name": "x"}, headers=h
    )

    assert taken.status_code == 409 and taken.json()["error"]["code"] == "EMAIL_TAKEN"
    assert same.status_code == 200  # a person may keep (or re-case) their own email
    assert missing.status_code == 404
    assert (await client.get(f"{URL}/not-a-uuid", headers=h)).status_code == 422


async def test_a_role_that_has_no_views_yet_cannot_be_given(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    target = await make_user(session, GlobalRole.DEVELOPER)

    response = await client.patch(
        f"{URL}/{target.id}", json={"role": "client"}, headers=headers(admin)
    )

    assert response.status_code == 422
    await session.refresh(target)
    assert target.global_role == "developer"


# --- deactivating -------------------------------------------------------------------------------


async def test_deactivated_person_is_locked_out_at_once_and_can_return(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    created = await create(client, admin)
    await accept(client, token_of(created))
    email = created["user"]["email"]
    signed_in = (await login(client, email, PASSWORD)).json()["access_token"]
    own = {"Authorization": f"Bearer {signed_in}"}
    assert (await client.get("/api/v1/auth/me", headers=own)).status_code == 200

    off = await client.post(f"{URL}/{created['user']['id']}/deactivate", headers=headers(admin))

    assert off.status_code == 200 and off.json()["is_active"] is False
    assert (await client.get("/api/v1/auth/me", headers=own)).status_code == 401
    assert (await login(client, email, PASSWORD)).status_code == 401

    on = await client.post(f"{URL}/{created['user']['id']}/activate", headers=headers(admin))
    assert on.json()["is_active"] is True
    assert (await client.get("/api/v1/auth/me", headers=own)).status_code == 200
    # activating or deactivating twice is harmless
    again = await client.post(f"{URL}/{created['user']['id']}/activate", headers=headers(admin))
    assert again.status_code == 200


async def test_an_administrator_cannot_demote_or_deactivate_themselves(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    other = await make_admin(session, "second@test.example")  # another admin exists, still refused
    h = headers(admin)

    role = await client.patch(f"{URL}/{admin.id}", json={"role": "pm"}, headers=h)
    off = await client.post(f"{URL}/{admin.id}/deactivate", headers=h)
    name = await client.patch(f"{URL}/{admin.id}", json={"name": "Renamed"}, headers=h)
    same_role = await client.patch(f"{URL}/{admin.id}", json={"role": "admin"}, headers=h)

    assert role.status_code == 409 and role.json()["error"]["code"] == "CANNOT_CHANGE_OWN_ROLE"
    assert off.status_code == 409 and off.json()["error"]["code"] == "CANNOT_DEACTIVATE_SELF"
    assert name.status_code == 200 and same_role.status_code == 200
    assert other.is_active


async def test_one_administrator_can_remove_another_while_one_remains(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    admin = await make_admin(session)
    other = await make_admin(session, "second@test.example")

    demoted = await client.patch(
        f"{URL}/{other.id}", json={"role": "developer"}, headers=headers(admin)
    )

    assert demoted.status_code == 200 and demoted.json()["role"] == "developer"


async def test_the_last_active_administrator_always_stays(session: AsyncSession) -> None:
    only = await make_admin(session)
    inactive = await make_admin(session, "off@test.example")
    inactive.is_active = False
    await session.flush()

    with pytest.raises(AppError) as error:
        await service._ensure_another_admin(session, only)
    assert error.value.status_code == 409 and error.value.code == "LAST_ADMIN"

    second = await make_admin(session, "second@test.example")
    await service._ensure_another_admin(session, only)  # a second active admin: fine
    assert second.is_active


# --- changing your own password -----------------------------------------------------------------


async def signed_in_user(session: AsyncSession) -> User:
    user = await make_user(session, GlobalRole.DEVELOPER, email="dev@test.example")
    user.password_hash = hash_password(PASSWORD)
    await session.flush()
    return user


async def change(client: httpx.AsyncClient, user: User, current: str, new: str) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": current, "new_password": new},
        headers=headers(user),
    )


async def test_user_changes_their_own_password(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    user = await signed_in_user(session)

    response = await change(client, user, PASSWORD, "my brand new password")

    assert response.status_code == 204 and response.content == b""
    assert (await login(client, user.email, PASSWORD)).status_code == 401
    assert (await login(client, user.email, "my brand new password")).status_code == 200


async def test_change_password_checks_the_current_password_and_the_rule(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    user = await signed_in_user(session)

    wrong = await change(client, user, "not my password", "my brand new password")
    same = await change(client, user, PASSWORD, PASSWORD)
    short = await change(client, user, PASSWORD, "short")

    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "WRONG_CURRENT_PASSWORD"
    assert same.status_code == 422 and same.json()["error"]["details"][0]["field"] == "new_password"
    assert short.status_code == 422
    assert (await login(client, user.email, PASSWORD)).status_code == 200  # unchanged


async def test_guessing_the_current_password_locks_the_account(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    user = await signed_in_user(session)

    for _ in range(3):
        await change(client, user, "guess", "my brand new password")
    right_but_locked = await change(client, user, PASSWORD, "my brand new password")

    assert right_but_locked.status_code == 400
    assert (await login(client, user.email, PASSWORD)).status_code == 401  # locked out of login too
    await session.refresh(user)
    assert verify_password(PASSWORD, user.password_hash or "")


async def test_change_password_needs_a_token_and_a_password(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    entra_only = await make_user(session, GlobalRole.DEVELOPER)  # no password hash

    anonymous = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "x", "new_password": PASSWORD},
    )
    no_password = await change(client, entra_only, "anything", "my brand new password")

    assert anonymous.status_code == 401
    assert no_password.status_code == 400
