"""Per-project statuses (Jira-style): defaults, add, rename, reorder, delete with a move target.

Categories keep the dashboards working whatever the PM names the statuses. A project always
keeps at least one `done` status.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import StatusCategory
from app.core.errors import AppError
from app.tasks import activity
from app.tasks.models import Task, WorkflowStatus
from app.tasks.schemas import StatusCreate, StatusOut, StatusUpdate
from app.users.models import User

DEFAULT_STATUSES: list[tuple[str, StatusCategory]] = [
    ("Backlog", StatusCategory.BACKLOG),
    ("To do", StatusCategory.TODO),
    ("In progress", StatusCategory.IN_PROGRESS),
    ("Code review", StatusCategory.IN_PROGRESS),
    ("Testing", StatusCategory.IN_PROGRESS),
    ("Blocked", StatusCategory.BLOCKED),
    ("Done", StatusCategory.DONE),
]


def _status_not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Status not found.")


def _duplicate_name(name: str) -> AppError:
    return AppError(
        409,
        "DUPLICATE_STATUS",
        f"This project already has a status named {name}.",
        [{"field": "name", "issue": "duplicate", "message": "This name is already used."}],
    )


def _last_done() -> AppError:
    return AppError(
        409,
        "LAST_DONE_STATUS",
        "A project needs at least one status in the 'done' category.",
    )


async def create_defaults(session: AsyncSession, project_id: uuid.UUID) -> list[WorkflowStatus]:
    """Called when a project is created. Does not commit."""
    rows = [
        WorkflowStatus(project_id=project_id, name=name, category=category.value, position=index)
        for index, (name, category) in enumerate(DEFAULT_STATUSES)
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def get_status(
    session: AsyncSession, project_id: uuid.UUID, status_id: uuid.UUID
) -> WorkflowStatus:
    status = await session.scalar(
        select(WorkflowStatus).where(
            WorkflowStatus.id == status_id, WorkflowStatus.project_id == project_id
        )
    )
    if status is None:
        raise _status_not_found()
    return status


async def project_statuses(session: AsyncSession, project_id: uuid.UUID) -> list[WorkflowStatus]:
    rows = await session.scalars(
        select(WorkflowStatus)
        .where(WorkflowStatus.project_id == project_id)
        .order_by(WorkflowStatus.position, WorkflowStatus.id)
    )
    return list(rows)


async def list_statuses(session: AsyncSession, project_id: uuid.UUID) -> list[StatusOut]:
    rows = await session.execute(
        select(Task.status_id, func.count(Task.id))
        .where(Task.project_id == project_id, Task.archived_at.is_(None))
        .group_by(Task.status_id)
    )
    counts: dict[uuid.UUID, int] = {status_id: count for status_id, count in rows.all()}
    return [
        StatusOut(
            id=s.id,
            name=s.name,
            category=s.category,
            position=s.position,
            task_count=counts.get(s.id, 0),
        )
        for s in await project_statuses(session, project_id)
    ]


async def status_out(
    session: AsyncSession, project_id: uuid.UUID, status_id: uuid.UUID
) -> StatusOut:
    for item in await list_statuses(session, project_id):
        if item.id == status_id:
            return item
    raise _status_not_found()


async def _done_count(session: AsyncSession, project_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count(WorkflowStatus.id)).where(
                WorkflowStatus.project_id == project_id,
                WorkflowStatus.category == StatusCategory.DONE.value,
            )
        )
        or 0
    )


async def _retarget_tasks(
    session: AsyncSession,
    project_id: uuid.UUID,
    source: tuple[uuid.UUID, str, str],
    dest: WorkflowStatus,
    actor: User,
) -> None:
    """Point tasks at `dest` and make their completed/blocked fields match its category.

    `source` is the (id, name, category) the tasks had before. Every moved task gets a history
    row: the status (or, for a category change of the same status, the category) and the
    blocked reason when it changes."""
    from_id, from_name, from_category = source
    fallback_reason = "Moved to a blocked status."
    is_blocked = dest.category == StatusCategory.BLOCKED.value
    affected = await session.execute(
        select(Task.id, Task.blocked_reason).where(
            Task.project_id == project_id, Task.status_id == from_id
        )
    )
    for task_id, old_reason in affected.all():
        changes: dict[str, list[object]] = {}
        if dest.id != from_id:
            changes["status"] = [from_name, dest.name]
        if dest.category != from_category:
            changes["status_category"] = [from_category, dest.category]
        new_reason = ((old_reason or "").strip() or fallback_reason) if is_blocked else None
        if new_reason != old_reason:
            changes["blocked_reason"] = [old_reason, new_reason]
        if changes:
            activity.record(session, task_id, actor.id, "updated", changes)

    now = datetime.now(UTC)
    values: dict[str, object] = {"status_id": dest.id, "version": Task.version + 1}
    if dest.category == StatusCategory.DONE.value:
        values["completed_at"] = func.coalesce(Task.completed_at, now)
    else:
        values["completed_at"] = None
    if dest.category == StatusCategory.BLOCKED.value:
        values["blocked_at"] = func.coalesce(Task.blocked_at, now)
        values["blocked_reason"] = func.coalesce(
            func.nullif(func.btrim(Task.blocked_reason), ""), fallback_reason
        )
    else:
        values["blocked_at"] = None
        values["blocked_reason"] = None
    await session.execute(
        update(Task).where(Task.project_id == project_id, Task.status_id == from_id).values(values)
    )


async def _ensure_name_free(
    session: AsyncSession, project_id: uuid.UUID, name: str, own_id: uuid.UUID | None = None
) -> None:
    query = select(WorkflowStatus.id).where(
        WorkflowStatus.project_id == project_id, func.lower(WorkflowStatus.name) == name.lower()
    )
    if own_id is not None:
        query = query.where(WorkflowStatus.id != own_id)
    taken = await session.scalar(query)
    if taken is not None:
        raise _duplicate_name(name)


async def create_status(
    session: AsyncSession, project_id: uuid.UUID, data: StatusCreate
) -> WorkflowStatus:
    await _ensure_name_free(session, project_id, data.name)
    last = await session.scalar(
        select(func.max(WorkflowStatus.position)).where(WorkflowStatus.project_id == project_id)
    )
    status = WorkflowStatus(
        project_id=project_id,
        name=data.name,
        category=data.category.value,
        position=(last if last is not None else -1) + 1,
    )
    session.add(status)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _duplicate_name(data.name) from None
    return status


async def update_status(
    session: AsyncSession,
    project_id: uuid.UUID,
    status_id: uuid.UUID,
    data: StatusUpdate,
    actor: User,
) -> WorkflowStatus:
    status = await get_status(session, project_id, status_id)
    old_category = status.category
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The request is not valid.",
            [{"field": "name", "issue": "required", "message": "Name is required."}],
        )
    if "category" in changes and changes["category"] is None:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The request is not valid.",
            [{"field": "category", "issue": "required", "message": "Category is required."}],
        )

    if "name" in changes:
        await _ensure_name_free(session, project_id, changes["name"], status.id)
    category_changed = False
    if "category" in changes and changes["category"].value != status.category:
        if (
            status.category == StatusCategory.DONE.value
            and await _done_count(session, project_id) < 2
        ):
            raise _last_done()
        status.category = changes["category"].value
        category_changed = True
    if "name" in changes:
        status.name = changes["name"]
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise _duplicate_name(changes["name"]) from None
    if category_changed:
        # Tasks already in this status must satisfy the new category's rules.
        await _retarget_tasks(
            session, project_id, (status.id, status.name, old_category), status, actor
        )
    await session.commit()
    await session.refresh(status)
    return status


async def reorder_statuses(
    session: AsyncSession, project_id: uuid.UUID, status_ids: list[uuid.UUID]
) -> None:
    existing = await project_statuses(session, project_id)
    if len(set(status_ids)) != len(status_ids) or set(status_ids) != {s.id for s in existing}:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Send every status of the project exactly once.",
            [
                {
                    "field": "status_ids",
                    "issue": "must_list_all_statuses",
                    "message": "Send every status of the project exactly once.",
                }
            ],
        )
    by_id = {s.id: s for s in existing}
    for position, status_id in enumerate(status_ids):
        by_id[status_id].position = position
    await session.commit()


async def delete_status(
    session: AsyncSession,
    project_id: uuid.UUID,
    status_id: uuid.UUID,
    move_to: uuid.UUID | None,
    actor: User,
) -> None:
    status = await get_status(session, project_id, status_id)
    if status.category == StatusCategory.DONE.value and await _done_count(session, project_id) < 2:
        raise _last_done()
    in_use = await session.scalar(
        select(func.count(Task.id)).where(
            Task.project_id == project_id, Task.status_id == status_id
        )
    )
    if in_use:
        if move_to is None:
            raise AppError(
                422,
                "MOVE_TO_REQUIRED",
                f"{in_use} task(s) use this status. Choose a status to move them to.",
                [
                    {
                        "field": "move_to",
                        "issue": "required",
                        "message": "Choose a status to move the tasks to.",
                    }
                ],
            )
        if move_to == status_id:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Choose a different status to move the tasks to.",
                [
                    {
                        "field": "move_to",
                        "issue": "same_status",
                        "message": "Must differ from the deleted status.",
                    }
                ],
            )
        destination = await get_status(session, project_id, move_to)
        await _retarget_tasks(
            session, project_id, (status.id, status.name, status.category), destination, actor
        )
    await session.delete(status)
    await session.commit()
