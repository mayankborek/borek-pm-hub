"""Status and task endpoints (F03, F04, F05)."""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, may_lead_projects, require, sees_all_projects
from app.common.enums import StatusCategory, TaskPriority
from app.common.validation import PageParam, PageSizeParam
from app.core.config import get_settings
from app.core.database import SessionDep
from app.core.errors import AppError
from app.projects import service as project_service
from app.projects.membership import lead_rights_in, project_access
from app.projects.models import Project
from app.tasks import csv_import, importer, labels, pdf_export, service, statuses, transfer
from app.tasks.models import Task, WorkflowStatus
from app.tasks.schemas import (
    AssigneeUpdate,
    BoardOut,
    ImportResultOut,
    LabelOut,
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
    creator_id: uuid.UUID | None = None,
    writable: bool = False,
) -> Project:
    """Load the project and apply `action`: people who cannot see the project get 404."""
    project = await project_service.get_project(session, project_id)
    access = await project_access(session, user, project)
    require(
        user, action, access.resource(project_id, assignee_id=assignee_id, creator_id=creator_id)
    )
    if writable:
        project_service.ensure_writable(project)  # archived or cancelled: read-only
    return project


async def _task_for(
    session: AsyncSession, user: User, task_id: uuid.UUID, action: Action, *, writable: bool = False
) -> Task:
    task = await service.get_task(session, task_id)
    await _project_for(
        session,
        user,
        task.project_id,
        action,
        assignee_id=task.assignee_id,
        creator_id=task.created_by,
        writable=writable,
    )
    if task.archived_at is not None:
        if not await lead_rights_in(session, user, task.project_id):
            raise service.not_found()
        if writable:
            raise AppError(409, "TASK_ARCHIVED", "The task is archived.")
    return task


def _cross_project_scope(user: User, filters: service.TaskFilters) -> ColumnElement[bool] | None:
    """Visibility for lists across projects. Archived tasks there are for Managers only; a PM asks
    for them per project, where lead rights can be checked."""
    if sees_all_projects(user):
        return None
    filters.include_archived = False
    return service.scope_for_member(user)


async def _limit_archived_to_leads(
    session: AsyncSession, user: User, project_id: uuid.UUID, filters: service.TaskFilters
) -> None:
    if filters.include_archived and not await lead_rights_in(session, user, project_id):
        filters.include_archived = False


def task_filters(
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=100, description="Search title or key")] = None,
    status_id: Annotated[list[uuid.UUID] | None, Query(max_length=50)] = None,
    category: Annotated[list[StatusCategory] | None, Query(max_length=10)] = None,
    priority: Annotated[list[TaskPriority] | None, Query(max_length=10)] = None,
    assignee_id: uuid.UUID | None = None,
    unassigned: bool = False,
    label: Annotated[str | None, Query(max_length=30)] = None,
    due_before: Annotated[date | None, Query(description="Due strictly before this date")] = None,
    due_after: Annotated[date | None, Query(description="Due strictly after this date")] = None,
    overdue: Annotated[bool, Query(description="Past due and not in a done status")] = False,
    milestone_id: Annotated[
        uuid.UUID | None, Query(description="Tasks linked to this milestone")
    ] = None,
    include_archived: Annotated[
        bool, Query(description="Managers, and PMs on projects they lead; ignored for others")
    ] = False,
) -> service.TaskFilters:
    if due_before and due_after and due_after >= due_before:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The request is not valid.",
            [
                {
                    "field": "due_after",
                    "issue": "after_due_before",
                    "message": "due_after must be before due_before.",
                }
            ],
        )
    return service.TaskFilters(
        q=q,
        status_ids=status_id,
        categories=category,
        priorities=priority,
        assignee_id=assignee_id,
        unassigned=unassigned,
        label=label.strip() if label else None,
        due_before=due_before,
        due_after=due_after,
        overdue=overdue,
        milestone_id=milestone_id,
        include_archived=include_archived and may_lead_projects(user),
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
    await statuses.update_status(session, project_id, status_id, body, user)
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
    await statuses.delete_status(session, project_id, status_id, move_to, user)


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
    lead_rights = await lead_rights_in(session, user, project_id)
    task = await service.create_task(session, project, user, body, lead_rights=lead_rights)
    response.headers["Location"] = f"/api/v1/tasks/{task.id}"
    return task


async def _read_csv_upload(upload: UploadFile) -> bytes:
    """The uploaded file in memory, refusing more than MAX_UPLOAD_MB. Nothing is kept on disk."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = bytearray()
    while chunk := await upload.read(1024 * 1024):
        data += chunk
        if len(data) > limit:
            raise AppError(
                413, "FILE_TOO_LARGE", f"Files can be at most {get_settings().max_upload_mb} MB."
            )
    return bytes(data)


@router.post("/projects/{project_id}/tasks/import", response_model=ImportResultOut)
async def import_project_tasks(
    project_id: uuid.UUID,
    file: UploadFile,
    user: CurrentUser,
    session: SessionDep,
    dry_run: Annotated[
        bool, Query(description="true (default): check and report only, nothing is saved")
    ] = True,
) -> ImportResultOut:
    """PM only: bring tasks in from a CSV or XLSX file (a Jira CSV export, or a file from our
    own export).

    Send the file with `dry_run=true` first to see what would happen, then again with
    `dry_run=false` to save it. Tasks whose issue key is already in the project are skipped, so
    running it twice is safe. Everything is saved in one transaction.
    """
    project = await _project_for(session, user, project_id, Action.TASK_IMPORT, writable=True)
    data = await _read_csv_upload(file)
    try:
        parsed = await run_in_threadpool(csv_import.parse_file, data, file.filename)
    except csv_import.ImportFileError as error:
        raise AppError(422, "IMPORT_BAD_FILE", str(error)) from None
    return await importer.import_tasks(session, project, user, parsed, dry_run=dry_run)


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
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> TaskListOut | BoardOut:
    await _project_for(session, user, project_id, Action.TASK_VIEW)
    await _limit_archived_to_leads(session, user, project_id, filters)
    filters.project_id = project_id
    if view == "board":
        return await service.board(session, project_id, filters, sort)
    items, total = await service.list_tasks(
        session, filters, sort=sort, page=page, page_size=page_size
    )
    return TaskListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/projects/{project_id}/labels", response_model=list[LabelOut])
async def list_project_labels(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[
        str | None, Query(max_length=30, description="Part of the label, any case")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=labels.MAX_LABEL_SUGGESTIONS)] = 20,
) -> list[LabelOut]:
    """Labels already used on the project's active tasks, most used first, for the label picker.
    Anyone who may see the project's tasks may read them. To create a label, save it on a task
    (`PATCH /tasks/{id}` with `labels`)."""
    await _project_for(session, user, project_id, Action.TASK_VIEW)
    return await labels.list_labels(session, project_id, q, limit)


# --- tasks across projects --------------------------------------------------------------------


@router.get("/tasks", response_model=TaskListOut)
async def list_tasks(
    user: CurrentUser,
    session: SessionDep,
    filters: Filters,
    project_id: uuid.UUID | None = None,
    sort: TaskSort = "-created_at",
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> TaskListOut:
    """Managers see tasks of every active project, everyone else those of their projects."""
    require(user, Action.PROJECT_LIST)  # roles without project views get 403, even as members
    filters.project_id = project_id
    scope = _cross_project_scope(user, filters)
    items, total = await service.list_tasks(
        session, filters, sort=sort, page=page, page_size=page_size, scope=scope
    )
    return TaskListOut(items=items, total=total, page=page, page_size=page_size)


XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ExportFormat = Annotated[
    Literal["csv", "xlsx", "pdf"],
    Query(
        description="csv (default) or xlsx: can be imported again. pdf: a readable task list "
        "(not for import)."
    ),
]


async def _filter_summary(session: AsyncSession, filters: service.TaskFilters) -> list[str]:
    """The filters in words, for the PDF heading (statuses and assignee by name)."""
    found: list[str] = []
    if filters.q:
        found.append(f'search "{filters.q}"')
    if filters.status_ids:
        names = await session.scalars(
            select(WorkflowStatus.name)
            .where(WorkflowStatus.id.in_(filters.status_ids))
            .order_by(WorkflowStatus.position)
        )
        found.append("status " + ", ".join(names))
    if filters.categories:
        found.append("category " + ", ".join(c.value.replace("_", " ") for c in filters.categories))
    if filters.priorities:
        found.append("priority " + ", ".join(p.value for p in filters.priorities))
    if filters.unassigned:
        found.append("unassigned")
    elif filters.assignee_id:
        assignee = await session.get(User, filters.assignee_id)
        found.append(f"assignee {assignee.name if assignee else 'unknown'}")
    if filters.label:
        found.append(f"label {filters.label}")
    if filters.due_after:
        found.append(f"due after {filters.due_after.isoformat()}")
    if filters.due_before:
        found.append(f"due before {filters.due_before.isoformat()}")
    if filters.overdue:
        found.append("overdue")
    if filters.include_archived:
        found.append("including archived")
    return found


async def _export_response(
    session: AsyncSession,
    tasks: list[TaskOut],
    filters: service.TaskFilters,
    *,
    name: str,
    title: str,
    file_format: str,
) -> Response:
    if file_format == "pdf":
        summary = await _filter_summary(session, filters)
        content = await run_in_threadpool(
            pdf_export.build_pdf,
            tasks,
            title=title,
            filters=summary,
            exported_at=datetime.now(UTC),
        )
        media_type = "application/pdf"
    elif file_format == "xlsx":
        content, media_type = transfer.build_xlsx(tasks), XLSX_TYPE
    else:
        content, media_type = transfer.build_csv(tasks), "text/csv; charset=utf-8"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}.{file_format}"'},
    )


_CSV_RESPONSE: dict[int | str, dict[str, object]] = {
    200: {
        "description": "CSV, XLSX or PDF file",
        "content": {
            "text/csv": {"schema": {"type": "string"}},
            XLSX_TYPE: {"schema": {"type": "string", "format": "binary"}},
            "application/pdf": {"schema": {"type": "string", "format": "binary"}},
        },
    }
}


@router.get("/projects/{project_id}/tasks/export", response_class=Response, responses=_CSV_RESPONSE)
async def export_project_tasks(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    filters: Filters,
    format: ExportFormat = "csv",
) -> Response:
    """Download the tasks of one project (same filters as the list) as a CSV, XLSX or PDF file.
    CSV and XLSX can be imported again, into this or another project; PDF is for reading."""
    project = await _project_for(session, user, project_id, Action.TASK_VIEW)
    await _limit_archived_to_leads(session, user, project_id, filters)
    filters.project_id = project_id
    tasks = await service.export_tasks(session, filters)
    return await _export_response(
        session,
        tasks,
        filters,
        name=f"tasks-{project.code}-{datetime.now(UTC).date().isoformat()}",
        title=f"{project.name} ({project.code})",
        file_format=format,
    )


@router.get("/tasks/export", response_class=Response, responses=_CSV_RESPONSE)
async def export_tasks(
    user: CurrentUser,
    session: SessionDep,
    filters: Filters,
    project_id: uuid.UUID | None = None,
    format: ExportFormat = "csv",
) -> Response:
    """Download what `GET /tasks` lists (same filters, same visibility) as a CSV, XLSX or PDF
    file."""
    require(user, Action.PROJECT_LIST)
    filters.project_id = project_id
    scope = _cross_project_scope(user, filters)
    tasks = await service.export_tasks(session, filters, scope=scope)
    if project_id is None:
        title = "all projects" if sees_all_projects(user) else "my projects"
    else:  # named only from tasks the user may see, so an unknown id reveals nothing
        title = tasks[0].project_name if tasks else "selected project"
    return await _export_response(
        session,
        tasks,
        filters,
        name=f"tasks-all-{datetime.now(UTC).date().isoformat()}",
        title=title,
        file_format=format,
    )


@router.get("/me/tasks", response_model=TaskListOut)
async def my_tasks(
    user: CurrentUser,
    session: SessionDep,
    filters: Filters,
    project_id: uuid.UUID | None = None,
    sort: TaskSort = "due_date",
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> TaskListOut:
    """My Work (F07): tasks assigned to the signed-in user across their active projects."""
    require(user, Action.MY_TASKS)
    filters.project_id = project_id
    filters.assignee_id = user.id  # always the caller; the `assignee_id` and `unassigned` filters
    filters.unassigned = False  # do not apply here
    scope = _cross_project_scope(user, filters)
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
    pm_only = service.DETAIL_FIELDS - service.SCHEDULE_FIELDS - service.PRIORITY_FIELDS
    if changed & pm_only:
        await _task_for(session, user, task_id, Action.TASK_EDIT_DETAILS, writable=True)
    if changed & service.PRIORITY_FIELDS:
        await _task_for(session, user, task_id, Action.TASK_EDIT_PRIORITY, writable=True)
    if changed & service.SCHEDULE_FIELDS:
        await _task_for(session, user, task_id, Action.TASK_EDIT_SCHEDULE, writable=True)
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
    """Archive (soft delete). The task stays in the database. Not in archived or cancelled
    projects; archiving an already archived task is harmless."""
    task = await _task_for(session, user, task_id, Action.TASK_ARCHIVE)
    project_service.ensure_writable(await project_service.get_project(session, task.project_id))
    await service.archive_task(session, task, user)
