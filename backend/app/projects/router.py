"""Project and project-member endpoints (F02)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, Resource, require
from app.common.enums import GlobalRole, ProjectStatus
from app.common.validation import PageParam, PageSizeParam
from app.core.database import SessionDep
from app.projects import service
from app.projects.membership import is_member
from app.projects.models import Project, ProjectMember
from app.projects.schemas import (
    MemberIn,
    MemberOut,
    MemberRoleUpdate,
    ProjectCreate,
    ProjectDetailOut,
    ProjectListOut,
    ProjectOut,
    ProjectUpdate,
    TaskSummary,
)
from app.users.models import User

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_out(project: Project, summary: TaskSummary | None = None) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        code=project.code,
        name=project.name,
        description=project.description,
        status=project.status,
        start_date=project.start_date,
        target_end_date=project.target_end_date,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
        version=project.version,
        task_summary=summary or TaskSummary(),
    )


def _member_out(member: ProjectMember, user: User) -> MemberOut:
    return MemberOut(
        user_id=user.id,
        name=user.name,
        email=user.email,
        project_role=member.project_role,
        granted_at=member.granted_at,
    )


async def _detail(session: AsyncSession, project: Project) -> ProjectDetailOut:
    summaries = await service.task_summaries(session, [project.id])
    members = await service.list_members(session, project.id)
    base = _project_out(project, summaries.get(project.id))
    return ProjectDetailOut(**base.model_dump(), members=[_member_out(m, u) for m, u in members])


async def _require_view(session: AsyncSession, user: User, project_id: uuid.UUID) -> Project:
    """Load the project and apply the view rule: non-members get 404, never a hint it exists."""
    project = await service.get_project(session, project_id)
    member = await is_member(session, user.id, project_id)
    require(user, Action.PROJECT_VIEW, Resource(project_id=project_id, is_member=member))
    if project.archived_at is not None and user.global_role != GlobalRole.PM:
        raise service.not_found()
    return project


@router.post("", response_model=ProjectDetailOut, status_code=201)
async def create_project(
    body: ProjectCreate, user: CurrentUser, session: SessionDep, response: Response
) -> ProjectDetailOut:
    require(user, Action.PROJECT_CREATE)
    project = await service.create_project(session, user, body)
    response.headers["Location"] = f"/api/v1/projects/{project.id}"
    return await _detail(session, project)


@router.get("", response_model=ProjectListOut)
async def list_projects(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100, description="Search name or code")] = None,
    status: ProjectStatus | None = None,
    include_archived: Annotated[bool, Query(description="PM only; ignored for developers")] = False,
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> ProjectListOut:
    require(user, Action.PROJECT_LIST)
    projects, total = await service.list_projects(
        session,
        user,
        q=q,
        status=status.value if status else None,
        include_archived=include_archived,
        page=page,
        page_size=page_size,
    )
    summaries = await service.task_summaries(session, [p.id for p in projects])
    return ProjectListOut(
        items=[_project_out(p, summaries.get(p.id)) for p in projects],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}", response_model=ProjectDetailOut)
async def get_project(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ProjectDetailOut:
    project = await _require_view(session, user, project_id)
    return await _detail(session, project)


@router.patch("/{project_id}", response_model=ProjectDetailOut)
async def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, user: CurrentUser, session: SessionDep
) -> ProjectDetailOut:
    await _require_manage(session, user, project_id, Action.PROJECT_UPDATE)
    project = await service.update_project(session, project_id, body)
    return await _detail(session, project)


@router.delete("/{project_id}", status_code=204)
async def archive_project(project_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    """Archive (soft delete). The project and its tasks stay in the database."""
    await _require_manage(session, user, project_id, Action.PROJECT_ARCHIVE)
    await service.archive_project(session, project_id)


async def _require_manage(
    session: AsyncSession, user: User, project_id: uuid.UUID, action: Action
) -> None:
    """PM-only actions on an existing project. Developers: 404 if not a member, else 403."""
    member = await is_member(session, user.id, project_id)
    require(user, action, Resource(project_id=project_id, is_member=member))
    await service.get_project(session, project_id)  # 404 for an unknown ID (PM)


@router.get("/{project_id}/members", response_model=list[MemberOut])
async def list_members(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[MemberOut]:
    await _require_view(session, user, project_id)
    return [_member_out(m, u) for m, u in await service.list_members(session, project_id)]


@router.post("/{project_id}/members", response_model=MemberOut, status_code=201)
async def add_member(
    project_id: uuid.UUID, body: MemberIn, user: CurrentUser, session: SessionDep
) -> MemberOut:
    await _require_manage(session, user, project_id, Action.MEMBER_MANAGE)
    project = await service.get_writable_project(session, project_id)
    member, member_user = await service.add_member(session, project, user, body)
    return _member_out(member, member_user)


@router.patch("/{project_id}/members/{user_id}", response_model=MemberOut)
async def change_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemberRoleUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> MemberOut:
    await _require_manage(session, user, project_id, Action.MEMBER_MANAGE)
    await service.get_writable_project(session, project_id)
    member, member_user = await service.change_member_role(
        session, project_id, user_id, body.project_role
    )
    return _member_out(member, member_user)


@router.delete("/{project_id}/members/{user_id}", status_code=204)
async def remove_member(
    project_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Remove a member. Their tasks in this project become unassigned (recorded in history)."""
    await _require_manage(session, user, project_id, Action.MEMBER_MANAGE)
    await service.get_writable_project(session, project_id)
    await service.remove_member(session, project_id, user_id, user)
