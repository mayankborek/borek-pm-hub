"""Role permissions and project access (Administrator handoff 10 + 11), plus the signed-in
user's own role matrix row for menus."""

import uuid

from fastapi import APIRouter

from app.access_policy import service
from app.access_policy.schemas import (
    MyPermissionsOut,
    PersonProjectAccessOut,
    PersonProjectsOut,
    RoleMatrixOut,
    SwitchUpdate,
)
from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require
from app.auth.policy import navigation_flags
from app.core.database import SessionDep

router = APIRouter(tags=["access policy"])


@router.get("/admin/role-permissions", response_model=RoleMatrixOut)
async def role_matrix(user: CurrentUser, session: SessionDep) -> RoleMatrixOut:
    """The role policy matrix: Manager, Project Manager, Account Manager, Developer (switches),
    Administrator and Client (fixed). `always` and `none` cells are read-only."""
    require(user, Action.ACCESS_POLICY_MANAGE)
    return await service.role_matrix(session)


@router.put("/admin/role-permissions/{role}/{permission}", response_model=RoleMatrixOut)
async def set_role_permission(
    role: str, permission: str, body: SwitchUpdate, user: CurrentUser, session: SessionDep
) -> RoleMatrixOut:
    """Switch one cell on or off; saved at once and applied to everyone with the role on their
    next request. 409 FIXED_POLICY for fixed roles or cells."""
    require(user, Action.ACCESS_POLICY_MANAGE)
    return await service.set_role_permission(session, user, role, permission, body.enabled)


@router.post("/admin/role-permissions/{role}/reset", response_model=RoleMatrixOut)
async def reset_role(role: str, user: CurrentUser, session: SessionDep) -> RoleMatrixOut:
    """Back to the product defaults for this role only."""
    require(user, Action.ACCESS_POLICY_MANAGE)
    return await service.reset_role(session, user, role)


@router.get("/admin/people/{user_id}/project-access", response_model=PersonProjectsOut)
async def person_projects(
    user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PersonProjectsOut:
    """The person's active projects (Manage, "All"), and which have switches set."""
    require(user, Action.ACCESS_POLICY_MANAGE)
    return await service.person_projects(session, user_id)


@router.get(
    "/admin/people/{user_id}/project-access/{project_id}",
    response_model=PersonProjectAccessOut,
)
async def person_project_access(
    user_id: uuid.UUID, project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PersonProjectAccessOut:
    """The six sections with every control: what the person can do now, the default, and
    whether a switch is saved. 409 NO_PROJECT_ACCESS when they no longer reach the project."""
    require(user, Action.ACCESS_POLICY_MANAGE)
    return await service.person_project_access(session, user_id, project_id)


@router.put(
    "/admin/people/{user_id}/project-access/{project_id}/{permission}",
    response_model=PersonProjectAccessOut,
)
async def set_project_control(
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    permission: str,
    body: SwitchUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> PersonProjectAccessOut:
    """Switch one control for this person in this project; saved at once. Returns the whole
    screen so the switches show the confirmed state."""
    require(user, Action.ACCESS_POLICY_MANAGE)
    return await service.set_project_control(
        session, user, user_id, project_id, permission, body.enabled
    )


@router.post(
    "/admin/people/{user_id}/project-access/{project_id}/sections/{section}/reset",
    response_model=PersonProjectAccessOut,
)
async def reset_section(
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    section: str,
    user: CurrentUser,
    session: SessionDep,
) -> PersonProjectAccessOut:
    """Reset to default: this section, person and project only."""
    require(user, Action.ACCESS_POLICY_MANAGE)
    return await service.reset_section(session, user, user_id, project_id, section)


@router.get("/me/permissions", response_model=MyPermissionsOut)
async def my_permissions(user: CurrentUser) -> MyPermissionsOut:
    """The signed-in user's role matrix row (for example `projects_menu`, `my_tasks`), so the
    frontend shows the same menus the server allows."""
    return MyPermissionsOut(role=user.global_role, permissions=navigation_flags(user))
