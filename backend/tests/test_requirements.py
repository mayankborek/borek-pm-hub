"""Requirements and client acceptance: versions, publishing, the client's answer against the exact
version, supersede, final states, and what the client sees."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole, ProjectRole
from app.organisations.models import Organisation
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
    dev: User
    outsider_dev: User
    contact: User
    other_contact: User
    project: Project
    other: Project
    internal: Project
    shown: dict[str, Any]
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


async def fails(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any, status: int
) -> dict[str, Any]:
    response = await call(client, user, method, path, body)
    assert response.status_code == status, response.text
    result: dict[str, Any] = response.json()
    return result


@pytest_asyncio.fixture
async def world(session: AsyncSession, client: httpx.AsyncClient) -> World:
    w = World()
    acme = Organisation(name="Acme", type="client")
    globex = Organisation(name="Globex", type="client")
    session.add_all([acme, globex])
    await session.flush()
    w.pm = await make_user(session, GlobalRole.PM, email="pm@borek.example")
    w.dev = await make_user(session, GlobalRole.DEVELOPER, email="dev@borek.example")
    w.outsider_dev = await make_user(session, GlobalRole.DEVELOPER, email="out@borek.example")
    w.contact = await make_user(session, GlobalRole.CLIENT, email="jordan@acme.example")
    w.contact.name = "Jordan Lee"
    w.contact.organisation_id = acme.id
    w.other_contact = await make_user(session, GlobalRole.CLIENT, email="sam@globex.example")
    w.other_contact.organisation_id = globex.id
    w.project = await make_project(session, w.pm.id, "WEB")
    w.other = await make_project(session, w.pm.id, "OTH")
    w.internal = await make_project(session, w.pm.id, "INT")
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


def reqs(w: World, project: Project | None = None) -> str:
    return f"/projects/{(project or w.project).id}/requirements"


def client_reqs(w: World, project: Project | None = None) -> str:
    return f"/client/projects/{(project or w.project).id}/requirements"


async def create(
    client: httpx.AsyncClient, w: World, criteria: list[str] | None = None, **extra: Any
) -> dict[str, Any]:
    body = {
        "title": "Sign-in page",
        "description": "Users sign in with email and password.",
        "acceptance_criteria": ["Wrong password shows an error"] if criteria is None else criteria,
        **extra,
    }
    result: dict[str, Any] = await ok(client, w.pm, "POST", reqs(w), body)
    return result


async def publish(client: httpx.AsyncClient, w: World, rid: str) -> dict[str, Any]:
    current = await ok(client, w.pm, "GET", f"{reqs(w)}/{rid}")
    result: dict[str, Any] = await ok(
        client, w.pm, "POST", f"{reqs(w)}/{rid}/publish", {"version": current["version"]}
    )
    return result


async def edit(client: httpx.AsyncClient, w: World, rid: str, **changes: Any) -> dict[str, Any]:
    current = await ok(client, w.pm, "GET", f"{reqs(w)}/{rid}")
    result: dict[str, Any] = await ok(
        client, w.pm, "PATCH", f"{reqs(w)}/{rid}", {"version": current["version"], **changes}
    )
    return result


async def answer(
    client: httpx.AsyncClient,
    w: World,
    rid: str,
    number: int,
    decision: str,
    comment: str | None = None,
) -> httpx.Response:
    return await call(
        client,
        w.contact,
        "POST",
        f"{client_reqs(w)}/{rid}/response",
        {"version_number": number, "decision": decision, "comment": comment},
    )


async def awaiting_input(client: httpx.AsyncClient, w: World) -> int:
    portal = await ok(client, w.contact, "GET", "/client/portal")
    value: int = portal["kpis"]["awaiting_input"]
    return value


# --- drafts -------------------------------------------------------------------------------------


async def test_a_new_requirement_is_a_draft_the_client_never_sees(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await create(client, world, ["  Shows an error ", "", "shows an error", "Logs in"])
    second = await create(client, world)

    assert (created["code"], second["code"]) == ("REQ-01", "REQ-02")
    assert created["status"] == "draft"
    assert (created["current_version"], created["published_version"]) == (1, None)
    assert created["versions"][0]["state"] == "draft"
    assert created["versions"][0]["acceptance_criteria"] == ["Shows an error", "Logs in"]
    listed = await ok(client, world.contact, "GET", client_reqs(world))
    assert listed == {
        "items": [],
        "counts": {
            "total": 0,
            "awaiting_acceptance": 0,
            "changes_requested": 0,
            "accepted": 0,
            "rejected": 0,
        },
    }
    await fails(client, world.contact, "GET", f"{client_reqs(world)}/{created['id']}", None, 404)
    assert (await answer(client, world, created["id"], 1, "accepted")).status_code == 404


async def test_drafts_can_be_edited_in_place(client: httpx.AsyncClient, world: World) -> None:
    created = await create(client, world)

    edited = await edit(client, world, created["id"], description="New text", title="Sign-in")

    assert edited["title"] == "Sign-in"
    assert edited["current_version"] == 1
    assert edited["versions"][0]["description"] == "New text"
    assert edited["version"] > created["version"]


# --- publishing and answering -------------------------------------------------------------------


async def test_publish_needs_criteria_and_an_external_project(
    client: httpx.AsyncClient, world: World
) -> None:
    empty = await create(client, world, [])
    error = await fails(
        client, world.pm, "POST", f"{reqs(world)}/{empty['id']}/publish", {"version": 1}, 422
    )
    assert error["error"]["details"][0]["field"] == "acceptance_criteria"

    internal = await ok(
        client,
        world.pm,
        "POST",
        reqs(world, world.internal),
        {"title": "x", "description": "y", "acceptance_criteria": ["z"]},
    )
    error = await fails(
        client,
        world.pm,
        "POST",
        f"{reqs(world, world.internal)}/{internal['id']}/publish",
        {"version": 1},
        409,
    )
    assert error["error"]["code"] == "NO_CLIENT"


async def test_client_accepts_the_published_version(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await create(client, world)
    published = await publish(client, world, created["id"])

    assert published["status"] == "awaiting_acceptance"
    assert published["published_version"] == 1
    assert published["versions"][0]["state"] == "awaiting_answer"
    assert await awaiting_input(client, world) == 1
    seen = await ok(client, world.contact, "GET", f"{client_reqs(world)}/{created['id']}")
    assert seen["awaiting_your_answer"] is True
    assert seen["current"]["number"] == 1
    assert seen["current"]["acceptance_criteria"] == ["Wrong password shows an error"]

    response = await answer(client, world, created["id"], 1, "accepted")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "accepted"
    assert response.json()["current"]["responded_by"] == "Jordan Lee"
    pm_view = await ok(client, world.pm, "GET", f"{reqs(world)}/{created['id']}")
    v1 = pm_view["versions"][0]
    assert (pm_view["status"], v1["state"], v1["response"]) == ("accepted", "answered", "accepted")
    assert v1["responded_by"]["id"] == str(world.contact.id)
    assert v1["responded_at"] is not None
    assert await awaiting_input(client, world) == 0
    listed = await ok(client, world.pm, "GET", reqs(world))
    assert listed["counts"]["accepted"] == 1


async def test_accepted_and_rejected_are_final(client: httpx.AsyncClient, world: World) -> None:
    created = await create(client, world)
    await publish(client, world, created["id"])
    await answer(client, world, created["id"], 1, "accepted")
    current = await ok(client, world.pm, "GET", f"{reqs(world)}/{created['id']}")

    path = f"{reqs(world)}/{created['id']}"
    edit_error = await fails(
        client, world.pm, "PATCH", path, {"version": current["version"], "title": "x"}, 409
    )
    publish_error = await fails(
        client, world.pm, "POST", f"{path}/publish", {"version": current["version"]}, 409
    )
    again = await answer(client, world, created["id"], 1, "rejected", "No")

    assert edit_error["error"]["code"] == "REQUIREMENT_CLOSED"
    assert publish_error["error"]["code"] == "REQUIREMENT_CLOSED"
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "NOT_AWAITING_ANSWER"


async def test_changes_requested_then_a_new_version_then_rejected(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await create(client, world)
    rid = created["id"]
    await publish(client, world, rid)
    asked = await answer(client, world, rid, 1, "changes_requested", "Add a reset link")
    assert asked.json()["status"] == "changes_requested"
    assert await awaiting_input(client, world) == 0

    draft = await edit(
        client,
        world,
        rid,
        acceptance_criteria=["Wrong password shows an error", "Reset link is shown"],
        change_note="Added the reset link",
    )

    assert (draft["current_version"], draft["published_version"]) == (2, 1)
    assert draft["has_unpublished_changes"] is True
    assert draft["status"] == "changes_requested"
    assert [v["state"] for v in draft["versions"]] == ["draft", "answered"]
    seen = await ok(client, world.contact, "GET", f"{client_reqs(world)}/{rid}")
    assert seen["current"]["number"] == 1  # the draft stays internal
    assert "Reset link is shown" not in str(seen)

    await publish(client, world, rid)
    seen = await ok(client, world.contact, "GET", f"{client_reqs(world)}/{rid}")
    assert seen["status"] == "awaiting_acceptance"
    assert seen["current"]["number"] == 2
    assert seen["current"]["change_note"] == "Added the reset link"
    assert [(h["number"], h["response"]) for h in seen["history"]] == [(1, "changes_requested")]
    assert seen["history"][0]["response_comment"] == "Add a reset link"

    old = await answer(client, world, rid, 1, "accepted")
    assert old.status_code == 409
    assert old.json()["error"]["code"] == "VERSION_NOT_OPEN"
    rejected = await answer(client, world, rid, 2, "rejected", "Out of scope now")
    assert rejected.json()["status"] == "rejected"
    pm_view = await ok(client, world.pm, "GET", f"{reqs(world)}/{rid}")
    assert [(v["number"], v["response"]) for v in pm_view["versions"]] == [
        (2, "rejected"),
        (1, "changes_requested"),
    ]


async def test_publishing_again_supersedes_an_unanswered_version(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await create(client, world)
    rid = created["id"]
    await publish(client, world, rid)
    await edit(client, world, rid, description="Better text")
    published = await publish(client, world, rid)

    assert [v["state"] for v in published["versions"]] == ["awaiting_answer", "superseded"]
    seen = await ok(client, world.contact, "GET", f"{client_reqs(world)}/{rid}")
    assert [seen["current"]["state"], seen["history"][0]["state"]] == [
        "awaiting_answer",
        "superseded",
    ]
    assert (await answer(client, world, rid, 1, "accepted")).status_code == 409
    assert (await answer(client, world, rid, 2, "accepted")).status_code == 200


async def test_publishing_twice_without_a_change_is_refused(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await create(client, world)
    published = await publish(client, world, created["id"])
    path = f"{reqs(world)}/{created['id']}"

    error = await fails(
        client, world.pm, "POST", f"{path}/publish", {"version": published["version"]}, 409
    )
    same = await fails(
        client,
        world.pm,
        "PATCH",
        path,
        {"version": published["version"], "description": published["versions"][0]["description"]},
        422,
    )

    assert error["error"]["code"] == "NOTHING_TO_PUBLISH"
    assert same["error"]["details"][0]["issue"] == "no_change"


async def test_only_meta_changes_keep_the_published_version(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await create(client, world)
    await publish(client, world, created["id"])

    edited = await edit(
        client, world, created["id"], title="Sign-in v1", owner_id=str(world.dev.id)
    )

    assert (edited["current_version"], edited["has_unpublished_changes"]) == (1, False)
    assert edited["status"] == "awaiting_acceptance"
    assert edited["owner"]["id"] == str(world.dev.id)


async def test_a_comment_is_needed_unless_accepting(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await create(client, world)
    await publish(client, world, created["id"])

    for decision in ("changes_requested", "rejected"):
        response = await answer(client, world, created["id"], 1, decision, "  ")
        assert response.status_code == 422, response.text


async def test_a_stale_version_is_refused(client: httpx.AsyncClient, world: World) -> None:
    created = await create(client, world)
    await edit(client, world, created["id"], title="Changed")

    error = await fails(
        client,
        world.pm,
        "PATCH",
        f"{reqs(world)}/{created['id']}",
        {"version": created["version"], "title": "Mine"},
        409,
    )
    assert error["error"]["code"] == "VERSION_CONFLICT"


# --- links and visibility -----------------------------------------------------------------------


async def test_owner_must_be_a_project_member(client: httpx.AsyncClient, world: World) -> None:
    error = await fails(
        client,
        world.pm,
        "POST",
        reqs(world),
        {"title": "x", "description": "y", "owner_id": str(world.outsider_dev.id)},
        422,
    )
    assert error["error"]["details"][0]["field"] == "owner_id"


async def test_the_client_sees_only_shown_milestones_and_no_emails(
    client: httpx.AsyncClient, world: World
) -> None:
    shown = await create(client, world, milestone_id=world.shown["id"], owner_id=str(world.dev.id))
    hidden = await create(client, world, milestone_id=world.hidden["id"])
    for r in (shown, hidden):
        await publish(client, world, r["id"])

    listed = await ok(client, world.contact, "GET", client_reqs(world))

    by_code = {r["code"]: r for r in listed["items"]}
    assert by_code["REQ-01"]["milestone"] == {
        "code": world.shown["code"],
        "name": "Delivery review",
    }
    assert by_code["REQ-01"]["owner"] == world.dev.name
    assert by_code["REQ-02"]["milestone"] is None
    assert "@borek.example" not in str(listed)
    assert listed["counts"]["awaiting_acceptance"] == 2
    assert await awaiting_input(client, world) == 2


async def test_other_clients_and_archived_requirements_are_not_found(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await create(client, world)
    await publish(client, world, created["id"])
    rid = created["id"]

    await fails(client, world.other_contact, "GET", client_reqs(world), None, 404)
    await fails(client, world.other_contact, "GET", f"{client_reqs(world)}/{rid}", None, 404)
    foreign = await call(
        client,
        world.other_contact,
        "POST",
        f"{client_reqs(world)}/{rid}/response",
        {"version_number": 1, "decision": "accepted"},
    )
    assert foreign.status_code == 404
    # The other organisation's own project does not contain it either.
    await fails(
        client, world.other_contact, "GET", f"{client_reqs(world, world.other)}/{rid}", None, 404
    )

    await ok(client, world.pm, "DELETE", f"{reqs(world)}/{rid}")

    assert (await ok(client, world.contact, "GET", client_reqs(world)))["items"] == []
    await fails(client, world.contact, "GET", f"{client_reqs(world)}/{rid}", None, 404)
    assert (await ok(client, world.pm, "GET", reqs(world)))["items"] == []
    assert await awaiting_input(client, world) == 0


async def test_developers_read_but_cannot_write_or_publish(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await create(client, world)

    listed = await ok(client, world.dev, "GET", reqs(world))
    await fails(client, world.dev, "POST", reqs(world), {"title": "x", "description": "y"}, 403)
    await fails(
        client, world.dev, "POST", f"{reqs(world)}/{created['id']}/publish", {"version": 1}, 403
    )
    await fails(client, world.outsider_dev, "GET", reqs(world), None, 404)
    await fails(
        client,
        world.pm,
        "POST",
        f"{client_reqs(world)}/{created['id']}/response",
        {"version_number": 1, "decision": "accepted"},
        403,
    )

    assert [r["code"] for r in listed["items"]] == ["REQ-01"]
