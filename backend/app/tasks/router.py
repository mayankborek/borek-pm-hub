"""Status and task endpoints (F03, F04, F05)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, Resource, require
from app.common.enums import GlobalRole, ProjectRole, StatusCategory, TaskPriority
from app.core.database import SessionDep
from app.core.errors import AppError
from app.projects import service as project_service
from app.projects.membership import project_role
from app.projects.models import Project
from app.tasks import service, statuses
from app.tasks.models import Task
from app.tasks.schemas import (
    AssigneeUpdate,
    BoardOut,
    StatusCreate,
    StatusOrder,
    StatusOut,
    StatusUpdate,
    TaskCreate,
    TaskListOut,
    TaskOut,
    TaskSort,
    TaskUpdate,
)
from app.users.models import User

router = APIRouter(tags=["tasks"])


# --- access helpers ---------------------------------------------------------------------------


async def _project_for(
    session: AsyncSession,
    user: User,
    project_id: uuid.UUID,
    action: Action,
    *,
    assignee_id: uuid.UUID | None = None,
    writable: bool = False,
) -> Project:
    """Load the project and apply `action`: developers who are not members get 404."""
    project = await project_service.get_project(session, project_id)
    role = await project_role(session, user.id, project_id)
    require(
        user,
        action,
        Resource(
            project_id=project_id,
            is_member=role is not None,
            is_project_lead=role == ProjectRole.PROJECT_LEAD.value,
            assignee_id=assignee_id,
        ),
    )
    if project.archived_at is not None:
        if user.global_role != GlobalRole.PM:
            raise project_service.not_found()
        if writable:
            raise AppError(409, "PROJECT_ARCHIVED", "The project is archived.")
    return project


async def _task_for(
    session: AsyncSession, user: User, task_id: uuid.UUID, action: Action, *, writable: bool = False
) -> Task:
    task = await service.get_task(session, task_id)
    await _project_for(
        session, user, task.project_id, action, assignee_id=task.assignee_id, writable=writable
    )
    if task.archived_at is not None:
        if user.global_role != GlobalRole.PM:
            raise service.not_found()
        if writable:
            raise AppError(409, "TASK_ARCHIVED", "The task is archived.")
    return task


def task_filters(
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=100, description="Search title or key")] = None,
    status_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    category: Annotated[list[StatusCategory] | None, Query()] = None,
    priority: Annotated[list[TaskPriority] | None, Query()] = None,
    assignee_id: uuid.UUID | None = None,
    unassigned: bool = False,
    label: Annotated[str | None, Query(max_length=30)] = None,
    due_before: Annotated[date | None, Query(description="Due strictly before this date")] = None,
    due_after: Annotated[date | None, Query(description="Due strictly after this date")] = None,
    overdue: Annotated[bool, Query(description="Past due and not in a done status")] = False,
    include_archived: Annotated[bool, Query(description="PM only; ignored for developers")] = False,
) -> service.TaskFilters:
    return service.TaskFilters(
        q=q,
        status_ids=status_id,
        categories=category,
        priorities=priority,
        assignee_id=assignee_id,
        unassigned=unassigned,
        label=label,
        due_before=due_before,
        due_after=due_after,
        overdue=overdue,
        include_archived=include_archived and user.global_role == GlobalRole.PM,
    )


Filters = Annotated[service.TaskFilters, Depends(task_filters)]


# --- statuses ---------------------------------------------------------------------------------


@router.get("/projects/{project_id}/statuses", response_model=list[StatusOut])
async def list_statuses(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[StatusOut]:
    await _project_for(session, user, project_id, Action.PROJECT_VIEW)
    return await statuses.list_statuses(session, project_id)


@router.post("/projects/{project_id}/statuses", response_model=StatusOut, status_code=201)
async def create_status(
    project_id: uuid.UUID, body: StatusCreate, user: CurrentUser, session: SessionDep
) -> StatusOut:
    await _project_for(session, user, project_id, Action.STATUS_MANAGE, writable=True)
    created = await statuses.create_status(session, project_id, body)
    return await statuses.status_out(session, project_id, created.id)


@router.put("/projects/{project_id}/statuses/order", response_model=list[StatusOut])
async def reorder_statuses(
    project_id: uuid.UUID, body: StatusOrder, user: CurrentUser, session: SessionDep
) -> list[StatusOut]:
    await _project_for(session, user, project_id, Action.STATUS_MANAGE, writable=True)
    await statuses.reorder_statuses(session, project_id, body.status_ids)
    return await statuses.list_statuses(session, project_id)


@router.patch("/projects/{project_id}/statuses/{status_id}", response_model=StatusOut)
async def update_status(
    project_id: uuid.UUID,
    status_id: uuid.UUID,
    body: StatusUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> StatusOut:
    await _project_for(session, user, project_id, Action.STATUS_MANAGE, writable=True)
    await statuses.update_status(session, project_id, status_id, body)
    return await statuses.status_out(session, project_id, status_id)


@router.delete("/projects/{project_id}/statuses/{status_id}", status_code=204)
async def delete_status(
    project_id: uuid.UUID,
    status_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    move_to: Annotated[
        uuid.UUID | None, Query(description="Status that receives the tasks of the deleted one")
    ] = None,
) -> None:
    """Delete a status. If tasks use it, `move_to` says where they go."""
    await _project_for(session, user, project_id, Action.STATUS_MANAGE, writable=True)
    await statuses.delete_status(session, project_id, status_id, move_to)


# --- tasks of a project -----------------------------------------------------------------------


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    project_id: uuid.UUID,
    body: TaskCreate,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
) -> TaskOut:
    project = await _project_for(session, user, project_id, Action.TASK_CREATE, writable=True)
    task = await service.create_task(
        session, project, user, body, is_pm=user.global_role == GlobalRole.PM
    )
    response.headers["Location"] = f"/api/v1/tasks/{task.id}"
    return task


@router.get("/projects/{project_id}/tasks", response_model=TaskListOut | BoardOut)
async def list_project_tasks(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    filters: Filters,
    view: Annotated[
        Literal["list", "board"], Query(description="board = grouped by status")
    ] = "list",
    sort: TaskSort = "-created_at",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TaskListOut | BoardOut:
    await _project_for(session, user, project_id, Action.TASK_VIEW)
    filters.project_id = project_id
    if view == "board":
        return await service.board(session, project_id, filters, sort)
    items, total = await service.list_tasks(
        session, filters, sort=sort, page=page, page_size=page_size
    )
    return TaskListOut(items=items, total=total, page=page, page_size=page_size)


# --- tasks across projects --------------------------------------------------------------------


@router.get("/tasks", response_model=TaskListOut)
async def list_tasks(
    user: CurrentUser,
    session: SessionDep,
    filters: Filters,
    project_id: uuid.UUID | None = None,
    sort: TaskSort = "-created_at",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TaskListOut:
    """PMs see tasks of every active project, developers those of their projects."""
    filters.project_id = project_id
    scope = None if user.global_role == GlobalRole.PM else service.scope_for_developer(user)
    items, total = await service.list_tasks(
        session, filters, sort=sort, page=page, page_size=page_size, scope=scope
    )
    return TaskListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/me/tasks", response_model=TaskListOut)
async def my_tasks(
    user: CurrentUser,
    session: SessionDep,
    filters: Filters,
    project_id: uuid.UUID | None = None,
    sort: TaskSort = "due_date",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TaskListOut:
    """My Work (F07): tasks assigned to the signed-in user across their active projects."""
    require(user, Action.MY_TASKS)
    filters.project_id = project_id
    filters.assignee_id = user.id  # always the caller; the `assignee_id` and `unassigned` filters
    filters.unassigned = False  # do not apply here
    scope = None if user.global_role == GlobalRole.PM else service.scope_for_developer(user)
    items, total = await service.list_tasks(
        session, filters, sort=sort, page=page, page_size=page_size, scope=scope
    )
    return TaskListOut(items=items, total=total, page=page, page_size=page_size)


# --- one task ---------------------------------------------------------------------------------


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> TaskOut:
    await _task_for(session, user, task_id, Action.TASK_VIEW)
    return await service.get_task_out(session, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID, body: TaskUpdate, user: CurrentUser, session: SessionDep
) -> TaskOut:
    task = await _task_for(session, user, task_id, Action.TASK_VIEW, writable=True)
    changed = body.model_fields_set - {"version"}
    if changed & service.DETAIL_FIELDS:
        await _task_for(session, user, task_id, Action.TASK_EDIT_DETAILS, writable=True)
    if changed & service.STATUS_FIELDS:
        await _task_for(session, user, task_id, Action.TASK_CHANGE_STATUS, writable=True)
    return await service.update_task(session, task, body, user)


@router.put("/tasks/{task_id}/assignee", response_model=TaskOut)
async def assign_task(
    task_id: uuid.UUID, body: AssigneeUpdate, user: CurrentUser, session: SessionDep
) -> TaskOut:
    """PM only: assign, reassign or unassign (`assignee_id: null`) a task."""
    task = await _task_for(session, user, task_id, Action.TASK_ASSIGN, writable=True)
    return await service.assign_task(session, task, body.assignee_id, body.version, user)


@router.delete("/tasks/{task_id}", status_code=204)
async def archive_task(task_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    """Archive (soft delete). The task stays in the database."""
    task = await _task_for(session, user, task_id, Action.TASK_ARCHIVE)
    await service.archive_task(session, task, user)
