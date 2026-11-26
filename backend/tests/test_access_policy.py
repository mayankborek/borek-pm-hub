"""Administrator handoff screens 10 + 11: role permissions matrix and a person's switches per
project. Precedence (Mayank 26.11.2026): fixed rules, then the project switch, then the role."""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.common.enums import GlobalRole
from app.core.config import get_settings
from app.projects.models import Project, ProjectMember
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_admin_users import SETTINGS, headers, make_admin
from tests.test_auth import build_app, client_for

ROLES = "/api/v1/admin/role-permissions"
PEOPLE = "/api/v1/admin/people"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    application = build_app(session)
    application.dependency_overrides[get_settings] = lambda: SETTINGS
    async with client_for(application) as http:
        yield http


class World:
    admin: User
    pm: User
    dev: User
    manager: User
    project: Project


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.admin = await make_admin(session)
    w.pm = await make_user(session, GlobalRole.PM)
    w.dev = await make_user(session)
    w.manager = await make_user(session, GlobalRole.MANAGER)
    w.project = await make_project(session, w.pm.id, "ACC")  # the PM leads it
    session.add(ProjectMember(project_id=w.project.id, user_id=w.dev.id))
    await session.flush()
    return w


def cell(matrix: dict, role: str, key: str) -> dict:
    column = next(c for c in matrix["roles"] if c["role"] == role)
    return next(p for p in column["permissions"] if p["key"] == key)


def has(found: dict, expected: dict) -> bool:
    return {key: found.get(key) for key in expected} == expected


def control(screen: dict, key: str) -> dict:
    return next(c for s in screen["sections"] for c in s["controls"] if c["key"] == key)


# --- screen 11 ----------------------------------------------------------------------------------


async def test_role_matrix_shows_the_design_defaults(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await client.get(ROLES, headers=headers(world.admin))
    assert response.status_code == 200
    matrix = response.json()
    assert [c["role"] for c in matrix["roles"]] == [
        "manager",
        "pm",
        "account_manager",
        "developer",
        "admin",
        "client",
    ]
    assert cell(matrix, "manager", "my_tasks")["value"] == "off"
    assert cell(matrix, "developer", "projects_menu")["value"] == "off"
    assert cell(matrix, "pm", "dashboard") == {
        "key": "dashboard",
        "label": "Dashboard",
        "section": "Workspace",
        "value": "always",
        "default": "always",
        "editable": False,
    }
    fixed = [c for c in matrix["roles"] if not c["editable"]]
    assert [c["role"] for c in fixed] == ["admin", "client"]
    assert all(not p["editable"] for c in fixed for p in c["permissions"])
    assert (await client.get(ROLES, headers=headers(world.manager))).status_code == 403


async def test_role_switch_applies_to_everyone_with_the_role_and_resets(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    url = f"{ROLES}/pm/create_projects"
    off = await client.put(url, json={"enabled": False}, headers=headers(world.admin))
    assert off.status_code == 200
    assert cell(off.json(), "pm", "create_projects")["value"] == "off"
    column = next(c for c in off.json()["roles"] if c["role"] == "pm")
    assert column["customised"] is True

    body = {"code": "NEW", "name": "New"}
    refused = await client.post("/api/v1/projects", json=body, headers=headers(world.pm))
    assert refused.status_code == 403
    flags = (await client.get("/api/v1/me/permissions", headers=headers(world.pm))).json()
    assert flags["permissions"]["create_projects"] is False

    reset = await client.post(f"{ROLES}/pm/reset", headers=headers(world.admin))
    assert cell(reset.json(), "pm", "create_projects")["value"] == "on"
    allowed = await client.post("/api/v1/projects", json=body, headers=headers(world.pm))
    assert allowed.status_code == 201
    actions = list(await session.scalars(select(AuditEvent.action)))
    assert "access_policy.role_changed" in actions and "access_policy.role_reset" in actions


async def test_manager_my_tasks_is_off_by_default_and_can_be_switched_on(
    client: httpx.AsyncClient, world: World
) -> None:
    assert (await client.get("/api/v1/me/tasks", headers=headers(world.manager))).status_code == 403
    await client.put(
        f"{ROLES}/manager/my_tasks", json={"enabled": True}, headers=headers(world.admin)
    )
    assert (await client.get("/api/v1/me/tasks", headers=headers(world.manager))).status_code == 200


async def test_fixed_roles_and_cells_cannot_change(client: httpx.AsyncClient, world: World) -> None:
    for url, status in (
        (f"{ROLES}/admin/my_tasks", 409),
        (f"{ROLES}/client/dashboard", 409),
        (f"{ROLES}/pm/dashboard", 409),  # "always"
        (f"{ROLES}/developer/create_projects", 409),  # "--"
        (f"{ROLES}/pm/unknown", 404),
        (f"{ROLES}/nobody/my_tasks", 404),
    ):
        response = await client.put(url, json={"enabled": False}, headers=headers(world.admin))
        assert response.status_code == status, url
    assert (
        await client.post(f"{ROLES}/admin/reset", headers=headers(world.admin))
    ).status_code == 409


async def test_developer_projects_menu_flag(client: httpx.AsyncClient, world: World) -> None:
    flags = (await client.get("/api/v1/me/permissions", headers=headers(world.dev))).json()
    assert flags["role"] == "developer"
    assert flags["permissions"]["projects_menu"] is False
    assert flags["permissions"]["my_tasks"] is True


# --- screen 10 ----------------------------------------------------------------------------------


async def test_person_projects_and_the_six_sections(
    client: httpx.AsyncClient, world: World
) -> None:
    listed = await client.get(
        f"{PEOPLE}/{world.dev.id}/project-access", headers=headers(world.admin)
    )
    assert listed.status_code == 200
    assert [(p["code"], p["access"]) for p in listed.json()["items"]] == [("ACC", "developer")]

    url = f"{PEOPLE}/{world.dev.id}/project-access/{world.project.id}"
    screen = (await client.get(url, headers=headers(world.admin))).json()
    assert [s["key"] for s in screen["sections"]] == [
        "project_overview",
        "tasks_and_board",
        "sprints_and_milestones",
        "change_requests",
        "people_and_access",
        "reports_and_status",
    ]
    assert sum(len(s["controls"]) for s in screen["sections"]) == 41
    assert control(screen, "create_tasks")["enabled"] is True
    assert control(screen, "delete_tasks")["enabled"] is False
    assert set(control(screen, "change_estimate")["linked_with"]) == {
        "edit_task_title_description",
        "change_task_type_labels",
    }


async def test_switches_change_what_the_person_can_do_in_that_project_only(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    other = await make_project(session, world.pm.id, "OTH")
    session.add(ProjectMember(project_id=other.id, user_id=world.dev.id))
    task = await make_task(session, world.project, world.pm.id)
    await session.flush()
    base = f"{PEOPLE}/{world.dev.id}/project-access/{world.project.id}"

    off = await client.put(
        f"{base}/create_tasks", json={"enabled": False}, headers=headers(world.admin)
    )
    assert off.status_code == 200
    assert has(control(off.json(), "create_tasks"), {"enabled": False, "customised": True})
    dev = headers(world.dev)
    blocked = await client.post(
        f"/api/v1/projects/{world.project.id}/tasks", json={"title": "x"}, headers=dev
    )
    assert blocked.status_code == 403
    elsewhere = await client.post(
        f"/api/v1/projects/{other.id}/tasks", json={"title": "x"}, headers=dev
    )
    assert elsewhere.status_code == 201

    # a switch can also give a right the role does not have by default
    on = await client.put(
        f"{base}/delete_tasks", json={"enabled": True}, headers=headers(world.admin)
    )
    assert control(on.json(), "delete_tasks")["enabled"] is True
    assert (await client.delete(f"/api/v1/tasks/{task.id}", headers=dev)).status_code == 204

    # reset only that section
    reset = await client.post(
        f"{base}/sections/tasks_and_board/reset", headers=headers(world.admin)
    )
    assert reset.status_code == 200
    assert has(control(reset.json(), "create_tasks"), {"enabled": True, "customised": False})
    assert control(reset.json(), "delete_tasks")["enabled"] is False


async def test_linked_controls_change_together(client: httpx.AsyncClient, world: World) -> None:
    base = f"{PEOPLE}/{world.pm.id}/project-access/{world.project.id}"
    screen = (
        await client.put(
            f"{base}/change_estimate", json={"enabled": False}, headers=headers(world.admin)
        )
    ).json()
    for key in ("change_estimate", "edit_task_title_description", "change_task_type_labels"):
        assert has(control(screen, key), {"enabled": False, "customised": True}), key


async def test_project_switch_wins_over_the_role_matrix(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    newcomer = await make_user(session)
    await client.put(
        f"{ROLES}/pm/manage_project_members", json={"enabled": False}, headers=headers(world.admin)
    )
    members = f"/api/v1/projects/{world.project.id}/members"
    body = {"user_id": str(newcomer.id)}
    assert (await client.post(members, json=body, headers=headers(world.pm))).status_code == 403

    await client.put(
        f"{PEOPLE}/{world.pm.id}/project-access/{world.project.id}/add_remove_members",
        json={"enabled": True},
        headers=headers(world.admin),
    )
    assert (await client.post(members, json=body, headers=headers(world.pm))).status_code == 201


async def test_fixed_people_and_projects_they_do_not_reach(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    client_contact = await make_user(session, GlobalRole.CLIENT)
    outsider = await make_user(session)
    for person in (world.admin, client_contact, outsider):
        url = f"{PEOPLE}/{person.id}/project-access/{world.project.id}"
        assert (await client.get(url, headers=headers(world.admin))).status_code == 409
        put = await client.put(
            f"{url}/create_tasks", json={"enabled": True}, headers=headers(world.admin)
        )
        assert put.status_code == 409
    listed = await client.get(
        f"{PEOPLE}/{client_contact.id}/project-access", headers=headers(world.admin)
    )
    assert has(listed.json(), {"editable": False, "items": []})
    fixed = await client.put(
        f"{PEOPLE}/{world.dev.id}/project-access/{world.project.id}/view_status_reports",
        json={"enabled": False},
        headers=headers(world.admin),
    )
    assert fixed.status_code == 409
    assert (
        await client.get(f"{PEOPLE}/{world.dev.id}/project-access", headers=headers(world.pm))
    ).status_code == 403
