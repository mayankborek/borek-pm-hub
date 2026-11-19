"""Project roadmap: phases, milestones, task links, and the client's view of them.

Dates are relative to today, because status and state are worked out from today's date.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole, ProjectRole
from app.organisations.models import Organisation
from app.projects.models import Project, ProjectMember
from app.tasks.models import Task
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
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
    contact: User
    project: Project
    other: Project


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    acme = Organisation(name="Acme", type="client")
    globex = Organisation(name="Globex", type="client")
    session.add_all([acme, globex])
    await session.flush()
    w.pm = await make_user(session, GlobalRole.PM, email="pm@borek.example")
    w.dev = await make_user(session, GlobalRole.DEVELOPER, email="dev@borek.example")
    w.contact = await make_user(session, GlobalRole.CLIENT, email="jordan@acme.example")
    w.contact.organisation_id = acme.id
    w.project = await make_project(session, w.pm.id, "WEB")
    w.other = await make_project(session, w.pm.id, "OTH")
    for project, org in ((w.project, acme), (w.other, globex)):
        project.project_type = "external"
        project.client_organisation_id = org.id
    session.add(
        ProjectMember(project_id=w.project.id, user_id=w.dev.id, project_role=ProjectRole.DEVELOPER)
    )
    await session.flush()
    return w


def h(user: User) -> dict[str, str]:
    return {HEADER: str(user.id)}


async def call(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any = None
) -> httpx.Response:
    return await client.request(method, API + path, headers=h(user), json=body)


async def ok(
    client: httpx.AsyncClient, user: User, method: str, path: str, body: Any = None
) -> Any:
    response = await call(client, user, method, path, body)
    assert response.status_code < 300, response.text
    return response.json() if response.content else None


async def phase(client: httpx.AsyncClient, w: World, name: str, start: int, end: int, **kw: Any):
    body = {"name": name, "start_date": day(start), "end_date": day(end), **kw}
    return await ok(client, w.pm, "POST", f"/projects/{w.project.id}/phases", body)


async def milestone(client: httpx.AsyncClient, w: World, name: str, due: int, **kw: Any):
    body = {"name": name, "due_date": day(due), **kw}
    return await ok(client, w.pm, "POST", f"/projects/{w.project.id}/milestones", body)


async def link(session: AsyncSession, task: Task, milestone_id: str) -> None:
    task.milestone_id = milestone_id  # type: ignore[assignment]
    await session.flush()


# --- the roadmap from the design ----------------------------------------------------------------


async def test_roadmap_matches_the_design(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    """Design completed, Development in progress with a late milestone, Testing and Launch not
    started; bars, completed share, diamonds and the date range."""
    w = world
    design = await phase(client, w, "Design", -30, -23)
    development = await phase(client, w, "Development", -22, -5)
    testing = await phase(client, w, "Testing", 2, 10)
    launch = await phase(client, w, "Launch & handover", 11, 18)
    approved = await milestone(client, w, "Design approved", -23, phase_id=design["id"])
    review = await milestone(client, w, "Delivery review", -15, phase_id=development["id"])
    await milestone(client, w, "Testing completed", 10, phase_id=testing["id"])
    await milestone(client, w, "Client handover", 18, phase_id=launch["id"])
    await ok(
        client,
        w.pm,
        "PATCH",
        f"/projects/{w.project.id}/milestones/{approved['id']}",
        {"version": approved["version"], "done": True},
    )
    for status in ("Done", "Done", "In progress", "To do"):
        await link(
            session, await make_task(session, w.project, w.pm.id, status=status), review["id"]
        )

    roadmap = await ok(client, w.dev, "GET", f"/projects/{w.project.id}/roadmap")

    assert roadmap["today"] == day(0)
    assert roadmap["range_start"] == day(-30)
    assert roadmap["range_end"] == day(18)
    rows = {
        p["name"]: (p["status"], p["progress"], [(m["name"], m["state"]) for m in p["milestones"]])
        for p in roadmap["phases"]
    }
    assert rows == {
        "Design": ("completed", 100, [("Design approved", "done")]),
        "Development": ("in_progress", 50, [("Delivery review", "late")]),
        "Testing": ("not_started", 0, [("Testing completed", "planned")]),
        "Launch & handover": ("not_started", 0, [("Client handover", "planned")]),
    }
    assert [p["name"] for p in roadmap["phases"]] == [
        "Design",
        "Development",
        "Testing",
        "Launch & handover",
    ]
    dev_phase = roadmap["phases"][1]
    assert dev_phase["is_late"] is True
    assert dev_phase["milestones"][0]["tasks_total"] == 4
    assert dev_phase["milestones"][0]["tasks_done"] == 2
    done = roadmap["phases"][0]["milestones"][0]
    assert done["done"] is True and done["completed_by"]["id"] == str(w.pm.id)
    assert roadmap["unphased_milestones"] == []


async def test_milestone_state_rules(client: httpx.AsyncClient, world: World) -> None:
    w = world
    started = await phase(client, w, "Build", -2, 20)
    planned = await milestone(client, w, "Planned", 5)
    in_phase = await milestone(client, w, "In started phase", 15, phase_id=started["id"])
    risky = await milestone(client, w, "Risky", 15, at_risk=True)
    late = await milestone(client, w, "Late", -1, at_risk=True)

    found = {
        m["name"]: m["state"]
        for m in await ok(client, w.pm, "GET", f"/projects/{w.project.id}/milestones")
    }

    assert found == {
        "Planned": "planned",
        "In started phase": "in_progress",
        "Risky": "at_risk",
        "Late": "late",  # a passed due date wins over the flag
    }
    assert planned["code"] == "M-01" and in_phase["code"] == "M-02"
    assert risky["code"] == "M-03" and late["code"] == "M-04"


async def test_a_started_task_puts_a_milestone_in_progress(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    m = await milestone(client, world, "Ship", 30)
    await link(
        session, await make_task(session, world.project, world.pm.id, status="In progress"), m["id"]
    )

    out = await ok(client, world.pm, "GET", f"/projects/{world.project.id}/milestones/{m['id']}")

    assert out["state"] == "in_progress"
    assert out["progress"] == 0
    assert [t["status_category"] for t in out["tasks"]] == ["in_progress"]


async def test_done_and_reopen(client: httpx.AsyncClient, world: World) -> None:
    m = await milestone(client, world, "Ship", 3)
    path = f"/projects/{world.project.id}/milestones/{m['id']}"

    done = await ok(client, world.pm, "PATCH", path, {"version": m["version"], "done": True})
    assert (done["state"], done["progress"], done["done"]) == ("done", 100, True)
    assert done["completed_at"] is not None

    reopened = await ok(
        client, world.pm, "PATCH", path, {"version": done["version"], "done": False}
    )
    assert (reopened["state"], reopened["done"], reopened["completed_by"]) == (
        "planned",
        False,
        None,
    )


async def test_phase_progress_without_tasks_counts_milestones(
    client: httpx.AsyncClient, world: World
) -> None:
    p = await phase(client, world, "Build", 1, 10)
    first = await milestone(client, world, "One", 4, phase_id=p["id"])
    await milestone(client, world, "Two", 8, phase_id=p["id"])
    await ok(
        client,
        world.pm,
        "PATCH",
        f"/projects/{world.project.id}/milestones/{first['id']}",
        {"version": 1, "done": True},
    )

    out = await ok(client, world.pm, "GET", f"/projects/{world.project.id}/phases/{p['id']}")

    assert (out["status"], out["progress"]) == ("in_progress", 50)
    assert (out["milestones_total"], out["milestones_done"]) == (2, 1)


# --- tasks link to milestones -------------------------------------------------------------------


async def test_pm_links_a_task_and_filters_by_milestone(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    m = await milestone(client, world, "Ship", 10)
    task = await make_task(session, world.project, world.pm.id, status="Done")
    await make_task(session, world.project, world.pm.id)

    out = await ok(
        client, world.pm, "PATCH", f"/tasks/{task.id}", {"version": 1, "milestone_id": m["id"]}
    )
    assert out["milestone_id"] == m["id"]

    listed = await ok(
        client, world.pm, "GET", f"/projects/{world.project.id}/tasks?milestone_id={m['id']}"
    )
    assert [t["id"] for t in listed["items"]] == [str(task.id)]
    shown = await ok(client, world.pm, "GET", f"/projects/{world.project.id}/milestones/{m['id']}")
    assert (shown["progress"], shown["tasks_total"]) == (100, 1)

    cleared = await ok(
        client,
        world.pm,
        "PATCH",
        f"/tasks/{task.id}",
        {"version": out["version"], "milestone_id": None},
    )
    assert cleared["milestone_id"] is None


async def test_create_task_with_a_milestone(client: httpx.AsyncClient, world: World) -> None:
    m = await milestone(client, world, "Ship", 10)

    out = await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.project.id}/tasks",
        {"title": "Build it", "milestone_id": m["id"]},
    )

    assert out["milestone_id"] == m["id"]


async def test_a_task_cannot_link_to_another_projects_milestone(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    foreign = await ok(
        client,
        world.pm,
        "POST",
        f"/projects/{world.other.id}/milestones",
        {"name": "Elsewhere", "due_date": day(5)},
    )
    task = await make_task(session, world.project, world.pm.id)

    response = await call(
        client,
        world.pm,
        "PATCH",
        f"/tasks/{task.id}",
        {"version": 1, "milestone_id": foreign["id"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["issue"] == "unknown_milestone"


async def test_developers_cannot_link_tasks(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    m = await milestone(client, world, "Ship", 10)
    task = await make_task(session, world.project, world.dev.id, assignee_id=world.dev.id)

    patch = await call(
        client, world.dev, "PATCH", f"/tasks/{task.id}", {"version": 1, "milestone_id": m["id"]}
    )
    create = await call(
        client,
        world.dev,
        "POST",
        f"/projects/{world.project.id}/tasks",
        {"title": "Mine", "milestone_id": m["id"]},
    )

    assert patch.status_code == 403
    assert create.status_code == 403


# --- archive, validation, conflicts -------------------------------------------------------------


async def test_archiving_a_milestone_unlinks_its_tasks_and_keeps_its_code_used(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    m = await milestone(client, world, "Ship", 10)
    task = await make_task(session, world.project, world.pm.id)
    await link(session, task, m["id"])

    await ok(client, world.pm, "DELETE", f"/projects/{world.project.id}/milestones/{m['id']}")

    out = await ok(client, world.pm, "GET", f"/tasks/{task.id}")
    assert out["milestone_id"] is None
    assert await ok(client, world.pm, "GET", f"/projects/{world.project.id}/milestones") == []
    gone = await call(client, world.pm, "GET", f"/projects/{world.project.id}/milestones/{m['id']}")
    assert gone.status_code == 404
    assert (await milestone(client, world, "Next", 12))["code"] == "M-02"


async def test_a_phase_with_milestones_cannot_be_archived(
    client: httpx.AsyncClient, world: World
) -> None:
    full = await phase(client, world, "Build", 1, 5)
    empty = await phase(client, world, "Spare", 6, 9)
    await milestone(client, world, "Ship", 5, phase_id=full["id"])
    base = f"/projects/{world.project.id}/phases"

    refused = await call(client, world.pm, "DELETE", f"{base}/{full['id']}")
    await ok(client, world.pm, "DELETE", f"{base}/{empty['id']}")

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "PHASE_HAS_MILESTONES"
    assert [p["name"] for p in await ok(client, world.pm, "GET", base)] == ["Build"]


async def test_reorder_phases(client: httpx.AsyncClient, world: World) -> None:
    a = await phase(client, world, "A", 1, 2)
    b = await phase(client, world, "B", 3, 4)
    base = f"/projects/{world.project.id}/phases"

    wrong = await call(client, world.pm, "PUT", f"{base}/order", {"phase_ids": [a["id"]]})
    await ok(client, world.pm, "PUT", f"{base}/order", {"phase_ids": [b["id"], a["id"]]})

    assert wrong.status_code == 422
    assert [p["name"] for p in await ok(client, world.pm, "GET", base)] == ["B", "A"]


async def test_validation(client: httpx.AsyncClient, world: World) -> None:
    base = f"/projects/{world.project.id}"
    p = await phase(client, world, "Build", 1, 5)
    outsider = str(world.contact.id)  # not a member of the project

    backwards = await call(
        client,
        world.pm,
        "POST",
        f"{base}/phases",
        {"name": "X", "start_date": day(5), "end_date": day(1)},
    )
    patch_backwards = await call(
        client, world.pm, "PATCH", f"{base}/phases/{p['id']}", {"version": 1, "end_date": day(0)}
    )
    bad_owner = await call(
        client,
        world.pm,
        "POST",
        f"{base}/milestones",
        {"name": "X", "due_date": day(1), "owner_id": outsider},
    )
    bad_phase = await call(
        client,
        world.pm,
        "POST",
        f"{base}/milestones",
        {"name": "X", "due_date": day(1), "phase_id": "00000000-0000-0000-0000-000000000000"},
    )
    null_name = await call(
        client, world.pm, "POST", f"{base}/milestones", {"name": "  ", "due_date": day(1)}
    )

    assert backwards.status_code == 422
    assert patch_backwards.status_code == 422
    assert bad_owner.json()["error"]["details"][0]["issue"] == "not_a_member"
    assert bad_phase.json()["error"]["details"][0]["issue"] == "unknown_phase"
    assert null_name.status_code == 422


async def test_owner_is_returned(client: httpx.AsyncClient, world: World) -> None:
    m = await milestone(
        client, world, "Ship", 3, owner_id=str(world.dev.id), completion_criteria="Signed off"
    )

    assert m["owner"]["id"] == str(world.dev.id)
    assert m["completion_criteria"] == "Signed off"


async def test_a_stale_version_is_refused(client: httpx.AsyncClient, world: World) -> None:
    m = await milestone(client, world, "Ship", 3)
    path = f"/projects/{world.project.id}/milestones/{m['id']}"
    await ok(client, world.pm, "PATCH", path, {"version": 1, "name": "Ship it"})

    stale = await call(client, world.pm, "PATCH", path, {"version": 1, "name": "Again"})

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


async def test_a_cancelled_project_roadmap_is_read_only(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.project.status = "cancelled"
    await session.flush()

    response = await call(
        client,
        world.pm,
        "POST",
        f"/projects/{world.project.id}/milestones",
        {"name": "X", "due_date": day(1)},
    )
    read = await call(client, world.pm, "GET", f"/projects/{world.project.id}/roadmap")

    assert response.status_code == 409
    assert read.status_code == 200


# --- the client's view --------------------------------------------------------------------------


async def test_client_roadmap_shows_only_visible_phases_and_milestones(
    client: httpx.AsyncClient, world: World
) -> None:
    w = world
    shown = await phase(client, w, "Design", -5, 5, client_visible=True)
    hidden = await phase(client, w, "Internal QA", 6, 9)
    await milestone(client, w, "Design approved", 5, phase_id=shown["id"], client_visible=True)
    await milestone(client, w, "Internal check", 4, phase_id=shown["id"])
    await milestone(client, w, "QA sign-off", 9, phase_id=hidden["id"], client_visible=True)
    await milestone(client, w, "Secret", 7)

    roadmap = await ok(client, w.contact, "GET", f"/client/projects/{w.project.id}/roadmap")

    assert [p["name"] for p in roadmap["phases"]] == ["Design"]
    assert set(roadmap["phases"][0]) == {
        "id",
        "name",
        "start_date",
        "end_date",
        "status",
        "progress",
        "milestones",
    }
    assert [m["name"] for m in roadmap["phases"][0]["milestones"]] == ["Design approved"]
    assert [m["name"] for m in roadmap["unphased_milestones"]] == ["QA sign-off"]
    milestone_out = roadmap["phases"][0]["milestones"][0]
    assert set(milestone_out) == {
        "id",
        "code",
        "name",
        "due_date",
        "state",
        "progress",
        "completed_on",
    }
    assert roadmap["range_start"] == day(-5)
    assert roadmap["range_end"] == day(9)


async def test_client_portal_has_upcoming_and_next_milestones(
    client: httpx.AsyncClient, world: World
) -> None:
    w = world
    done = await milestone(client, w, "Kick-off", -3, client_visible=True)
    await ok(
        client,
        w.pm,
        "PATCH",
        f"/projects/{w.project.id}/milestones/{done['id']}",
        {"version": 1, "done": True},
    )
    await milestone(client, w, "Beta", 7, client_visible=True)
    await milestone(client, w, "Hidden", 2)

    portal = await ok(client, w.contact, "GET", "/client/portal")
    detail = await ok(client, w.contact, "GET", f"/client/projects/{w.project.id}")

    assert [m["name"] for m in portal["upcoming_milestones"]] == ["Beta"]
    assert portal["upcoming_milestones"][0]["project_name"] == w.project.name
    assert portal["projects"][0]["next_milestone"]["name"] == "Beta"
    assert [m["name"] for m in detail["milestones"]] == ["Kick-off", "Beta"]
    assert detail["milestones"][0]["completed_on"] == day(0)


async def test_client_cannot_see_another_organisations_roadmap(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await call(
        client, world.contact, "GET", f"/client/projects/{world.other.id}/roadmap"
    )
    internal = await call(client, world.contact, "GET", f"/projects/{world.project.id}/roadmap")

    assert response.status_code == 404
    assert internal.status_code in (403, 404)
