"""Manager > Team: workload (open, overdue, remaining effort in person-days) and capacity
(reservations against working schedules), using the checks from the Manager Role Guide
(Capacity 7), plus schedules and reservations."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.capacity.service import add_months, status_of
from app.common.enums import GlobalRole, ProjectRole
from app.organisations.models import Organisation
from app.projects.models import Project, ProjectMember
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for

API = "/api/v1"
TODAY = datetime.now(UTC).date()
# A Monday well ahead, so week maths never depends on the day the tests run.
WEEK = TODAY + timedelta(days=(7 - TODAY.weekday()) % 7 + 14)


def iso(d: date) -> str:
    return d.isoformat()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


class World:
    manager: User
    admin: User
    pm: User
    mia: User
    noah: User
    part_timer: User
    ai: Project
    web: Project


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
async def world(session: AsyncSession) -> World:
    w = World()
    org = Organisation(name="BRECO", type="client")
    session.add(org)
    await session.flush()
    w.manager = await make_user(session, GlobalRole.MANAGER, email="boss@borek.example")
    w.admin = await make_user(session, GlobalRole.ADMIN, email="admin@borek.example")
    w.pm = await make_user(session, GlobalRole.PM, email="pm@borek.example")
    w.mia = await make_user(session, GlobalRole.DEVELOPER, email="mia@borek.example")
    w.noah = await make_user(session, GlobalRole.DEVELOPER, email="noah@borek.example")
    w.part_timer = await make_user(session, GlobalRole.DEVELOPER, email="part@borek.example")
    w.mia.name, w.noah.name, w.part_timer.name = "Mia Chen", "Noah Patel", "Pat Part"
    w.ai = await make_project(session, w.pm.id, "AIO")
    w.web = await make_project(session, w.pm.id, "WEB")
    w.web.project_type = "external"
    w.web.client_organisation_id = org.id
    for project in (w.ai, w.web):
        for dev in (w.mia, w.noah, w.part_timer):
            session.add(
                ProjectMember(
                    project_id=project.id, user_id=dev.id, project_role=ProjectRole.DEVELOPER
                )
            )
    await session.commit()
    return w


async def reserve(
    client: httpx.AsyncClient,
    w: World,
    project: Project,
    user: User,
    start: date,
    end: date,
    hours: float,
) -> dict[str, Any]:
    result: dict[str, Any] = await ok(
        client,
        w.pm,
        "POST",
        f"/projects/{project.id}/reservations",
        {
            "user_id": str(user.id),
            "start_date": iso(start),
            "end_date": iso(end),
            "hours_per_week": hours,
        },
    )
    return result


async def capacity_of(
    client: httpx.AsyncClient, w: World, weeks: int = 2, start: date = WEEK
) -> dict[str, dict[str, Any]]:
    body = await ok(client, w.manager, "GET", f"/manager/capacity?start={iso(start)}&weeks={weeks}")
    return {p["person"]["name"]: p for p in body["people"]}


# --- capacity (Manager Role Guide, Capacity 7) --------------------------------------------------


def test_thresholds_on_the_unrounded_total() -> None:
    assert status_of(40, 34) == (85.0, "near_capacity")
    assert status_of(40, 40) == (100.0, "near_capacity")
    assert status_of(40, 44)[1] == "overallocated"
    assert status_of(40, 31.9)[1] == "available"
    assert status_of(0, 0) == (None, "unavailable")
    assert status_of(0, 5) == (None, "conflict")
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)


async def test_guide_worked_example_85_25_and_110(client: httpx.AsyncClient, world: World) -> None:
    await reserve(client, world, world.ai, world.mia, WEEK, WEEK + timedelta(days=13), 34)
    await reserve(client, world, world.web, world.mia, WEEK, WEEK + timedelta(days=4), 10)

    mia = (await capacity_of(client, world))["Mia Chen"]

    first, second = mia["weeks"]
    assert (first["available_hours"], first["reserved_hours"]) == (40, 44)
    assert first["total_percent"] == 110
    assert first["capacity_left"] == -4
    assert first["status"] == "overallocated"
    assert {p["project"]["code"]: p["percent"] for p in first["projects"]} == {
        "AIO": 85,
        "WEB": 25,
    }
    assert (second["total_percent"], second["status"]) == (85, "near_capacity")
    # The timeline is split where Website Development stops.
    assert [(s["start"], s["end"], s["status"]) for s in mia["segments"]] == [
        (iso(WEEK), iso(WEEK + timedelta(days=4)), "overallocated"),
        (iso(WEEK + timedelta(days=7)), iso(WEEK + timedelta(days=11)), "near_capacity"),
    ]
    assert mia["has_engagements"] is True


async def test_two_day_booking_bar_50_and_week_20(client: httpx.AsyncClient, world: World) -> None:
    # Guide, Capacity 3: two days at 4 h/day (20 h/week over Mon-Fri) with an 8-hour day.
    await reserve(client, world, world.ai, world.mia, WEEK, WEEK + timedelta(days=1), 20)

    mia = (await capacity_of(client, world, weeks=1))["Mia Chen"]

    (bar,) = mia["segments"]
    assert (bar["start"], bar["end"]) == (iso(WEEK), iso(WEEK + timedelta(days=1)))
    assert (bar["available_hours"], bar["reserved_hours"], bar["total_percent"]) == (16, 8, 50)
    week = mia["weeks"][0]
    assert (week["available_hours"], week["reserved_hours"], week["total_percent"]) == (40, 8, 20)
    assert week["status"] == "available"


async def test_part_time_schedule_and_overlap_only_on_shared_days(
    client: httpx.AsyncClient, world: World
) -> None:
    await ok(
        client,
        world.manager,
        "PUT",
        f"/manager/people/{world.part_timer.id}/schedule",
        {"weekly_hours": 20, "working_days": [1, 2, 3, 4, 5]},
    )
    await reserve(client, world, world.ai, world.part_timer, WEEK, WEEK + timedelta(days=4), 10)
    # Two bookings that overlap on Wednesday only: 8 h/week each over Mon-Fri.
    await reserve(client, world, world.ai, world.noah, WEEK, WEEK + timedelta(days=2), 40)
    await reserve(
        client, world, world.web, world.noah, WEEK + timedelta(days=2), WEEK + timedelta(days=4), 40
    )

    people = await capacity_of(client, world, weeks=1)

    part = people["Pat Part"]
    assert part["schedule"] == {
        "weekly_hours": 20,
        "working_days": [1, 2, 3, 4, 5],
        "hours_per_day": 4,
        "source": "personal",
    }
    assert (part["weeks"][0]["total_percent"], part["weeks"][0]["status"]) == (50, "available")
    noah = people["Noah Patel"]
    assert [(s["start"], s["end"], s["total_percent"]) for s in noah["segments"]] == [
        (iso(WEEK), iso(WEEK + timedelta(days=1)), 100),
        (iso(WEEK + timedelta(days=2)), iso(WEEK + timedelta(days=2)), 200),
        (iso(WEEK + timedelta(days=3)), iso(WEEK + timedelta(days=4)), 100),
    ]


async def test_free_labels_and_summary(client: httpx.AsyncClient, world: World) -> None:
    far = TODAY + timedelta(days=200)
    await reserve(client, world, world.ai, world.mia, TODAY, far, 40)  # fully booked for months
    await reserve(client, world, world.web, world.noah, WEEK, WEEK + timedelta(days=4), 20)

    body = await ok(client, world.manager, "GET", f"/manager/capacity?start={iso(WEEK)}&weeks=1")
    people = {p["person"]["name"]: p for p in body["people"]}

    working_today = TODAY.isoweekday() <= 5
    assert people["Mia Chen"]["free_today"] is False
    assert people["Pat Part"]["free_today"] is working_today
    assert people["Mia Chen"]["next_unallocated_day"] > iso(far)
    noah = people["Noah Patel"]
    if working_today and TODAY < WEEK:
        assert noah["next_unallocated_day"] == iso(TODAY)
        assert noah["free_until"] == iso(WEEK - timedelta(days=1))  # a bounded free window
    assert people["Pat Part"]["has_engagements"] is False
    summary = body["summary"]
    assert summary["free_within_3_months"] == len(body["people"]) - 1  # all but Mia
    assert summary["without_engagements"] == len(body["people"]) - 2
    assert body["timezone"] == "UTC"
    assert body["thresholds"] == {"near_capacity": 80, "overallocated": 100}
    assert (body["period_start"], body["period_end"]) == (iso(WEEK), iso(WEEK + timedelta(days=6)))


async def test_zero_hours_is_unavailable_or_a_conflict(
    client: httpx.AsyncClient, world: World
) -> None:
    for person in (world.mia, world.noah):
        await ok(
            client,
            world.manager,
            "PUT",
            f"/manager/people/{person.id}/schedule",
            {"weekly_hours": 0, "working_days": [1, 2, 3, 4, 5]},
        )
    await reserve(client, world, world.ai, world.mia, WEEK, WEEK + timedelta(days=4), 10)

    people = await capacity_of(client, world, weeks=1)

    assert people["Mia Chen"]["weeks"][0]["status"] == "conflict"
    assert people["Mia Chen"]["weeks"][0]["total_percent"] is None
    assert people["Noah Patel"]["weeks"][0]["status"] == "unavailable"
    assert people["Noah Patel"]["free_today"] is False


async def test_tasks_never_change_capacity(
    client: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    await reserve(client, world, world.ai, world.mia, WEEK, WEEK + timedelta(days=4), 34)
    before = (await capacity_of(client, world, weeks=1))["Mia Chen"]["weeks"]
    await make_task(session, world.ai, world.pm.id, assignee_id=world.mia.id)
    await session.commit()

    after = (await capacity_of(client, world, weeks=1))["Mia Chen"]["weeks"]

    assert before == after


# --- reservations and schedules -----------------------------------------------------------------


async def test_reservation_rules(client: httpx.AsyncClient, world: World) -> None:
    base = f"/projects/{world.ai.id}/reservations"
    outsider = await call(
        client,
        world.pm,
        "POST",
        base,
        {
            "user_id": str(world.manager.id),
            "start_date": iso(WEEK),
            "end_date": iso(WEEK),
            "hours_per_week": 8,
        },
    )
    assert outsider.status_code == 422
    backwards = await call(
        client,
        world.pm,
        "POST",
        base,
        {
            "user_id": str(world.mia.id),
            "start_date": iso(WEEK),
            "end_date": iso(WEEK - timedelta(days=1)),
            "hours_per_week": 8,
        },
    )
    assert backwards.status_code == 422
    created = await reserve(client, world, world.ai, world.mia, WEEK, WEEK + timedelta(days=4), 34)
    assert created["person"]["name"] == "Mia Chen"
    assert created["hours_per_week"] == 34

    stale = await call(
        client, world.pm, "PATCH", f"{base}/{created['id']}", {"version": 9, "hours_per_week": 20}
    )
    assert stale.status_code == 409
    changed = await ok(
        client,
        world.manager,
        "PATCH",
        f"{base}/{created['id']}",
        {"version": 1, "hours_per_week": 20},
    )
    assert changed["hours_per_week"] == 20
    assert (await call(client, world.mia, "GET", base)).status_code == 403  # developers: no

    await ok(client, world.pm, "DELETE", f"{base}/{created['id']}")

    assert await ok(client, world.pm, "GET", base) == []
    assert (await capacity_of(client, world, weeks=1))["Mia Chen"]["segments"] == []


async def test_schedules(client: httpx.AsyncClient, world: World) -> None:
    default = await ok(client, world.manager, "GET", "/manager/schedule")
    assert default == {
        "weekly_hours": 40,
        "working_days": [1, 2, 3, 4, 5],
        "hours_per_day": 8,
        "source": "workspace",
    }
    changed = await ok(
        client,
        world.admin,
        "PUT",
        "/manager/schedule",
        {"weekly_hours": 36, "working_days": [5, 1, 2, 3, 4, 4]},
    )
    assert (changed["working_days"], changed["hours_per_day"]) == ([1, 2, 3, 4, 5], 7.2)
    bad = await call(
        client, world.manager, "PUT", "/manager/schedule", {"weekly_hours": 40, "working_days": [8]}
    )
    assert bad.status_code == 422

    path = f"/manager/people/{world.mia.id}/schedule"
    assert (await ok(client, world.manager, "GET", path))["source"] == "workspace"
    await ok(client, world.manager, "PUT", path, {"weekly_hours": 16, "working_days": [1, 2]})
    assert (await ok(client, world.manager, "GET", path))["hours_per_day"] == 8
    cleared = await ok(client, world.manager, "DELETE", path)
    assert (cleared["source"], cleared["weekly_hours"]) == ("workspace", 36)
    assert (
        await call(client, world.manager, "GET", f"/manager/people/{world.admin.id}/schedule")
    ).status_code == 404
    assert (
        await call(client, world.pm, "PUT", path, {"weekly_hours": 1, "working_days": [1]})
    ).status_code == 403


# --- workload -----------------------------------------------------------------------------------


async def test_workload_counts_effort_and_unassigned(
    client: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    async def task(project: Project, user: User | None, **fields: Any) -> None:
        await make_task(
            session, project, world.pm.id, assignee_id=user.id if user else None, **fields
        )

    yesterday = TODAY - timedelta(days=1)
    await task(world.ai, world.mia, estimate_value=16, estimate_unit="hours", due_date=yesterday)
    await task(world.ai, world.mia, estimate_value=1, estimate_unit="weeks")  # 5 PD
    await task(world.web, world.mia, estimate_value=240, estimate_unit="minutes")  # 0.5 PD
    await task(world.web, world.mia)  # not estimated
    await task(world.ai, world.mia, estimate_value=80, estimate_unit="hours", status="Done")
    await task(world.ai, world.noah, due_date=yesterday)  # only unestimated work
    await task(world.ai, None, estimate_value=8, estimate_unit="hours")  # unassigned
    await session.commit()

    body = await ok(client, world.manager, "GET", "/manager/workload")

    assert body["hours_per_day"] == 8
    people = body["people"]
    assert [p["person"]["name"] for p in people] == ["Mia Chen", "Noah Patel"]
    mia, noah = people
    assert (mia["open"], mia["overdue"], mia["effort_pd"], mia["unestimated"]) == (4, 1, 7.5, 1)
    assert {p["project"]["code"]: (p["open"], p["effort_pd"]) for p in mia["projects"]} == {
        "AIO": (2, 7.0),
        "WEB": (2, 0.5),
    }
    assert {p["project"]["code"]: p["client"] for p in mia["projects"]} == {
        "AIO": None,
        "WEB": "BRECO",
    }
    assert (noah["open"], noah["overdue"], noah["effort_pd"], noah["unestimated"]) == (
        1,
        1,
        None,
        1,
    )
    assert body["unassigned"] == {"open": 1, "overdue": 0, "effort_pd": 1.0, "unestimated": 0}
    assert body["summary"] == {
        "people_with_open_work": 2,
        "projects_with_open_work": 2,
        "open": 6,
        "overdue": 2,
        "effort_pd": 8.5,
        "unestimated": 2,
        "most_open": {"id": str(world.mia.id), "name": "Mia Chen", "job_title": None},
        "most_open_count": 4,
    }


async def test_team_views_are_for_managers(client: httpx.AsyncClient, world: World) -> None:
    for user in (world.pm, world.mia, world.admin):
        for path in ("/manager/workload", "/manager/capacity"):
            assert (await call(client, user, "GET", path)).status_code == 403
