"""Task links: rules live here, routers check permissions. Both tasks get a history row."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import AppError
from app.task_links.models import LinkType, TaskLink
from app.task_links.schemas import KINDS, LABELS, LinkedTask, LinkIn, TaskLinkOut, kind_of
from app.tasks import activity
from app.tasks.models import Task, WorkflowStatus
from app.tasks.schemas import StatusBrief, UserBrief
from app.users.models import User

MAX_LINKS = 100  # per task


def _brief(user: User) -> UserBrief:
    return UserBrief(id=user.id, name=user.name, email=user.email)


def _invalid(issue: str, message: str) -> AppError:
    return AppError(
        422,
        "VALIDATION_ERROR",
        "The request is not valid.",
        [{"field": "task_id", "issue": issue, "message": message}],
    )


async def list_links(
    session: AsyncSession, task: Task, *, include_archived: bool = False
) -> list[TaskLinkOut]:
    """Links of the task, read from its side. Archived linked tasks are left out for people
    without lead rights."""
    other = aliased(Task)
    creator = aliased(User)
    assignee = aliased(User)
    query = (
        select(TaskLink, other, WorkflowStatus, assignee, creator)
        .join(
            other,
            or_(
                (TaskLink.source_task_id == task.id) & (other.id == TaskLink.target_task_id),
                (TaskLink.target_task_id == task.id) & (other.id == TaskLink.source_task_id),
            ),
        )
        .join(WorkflowStatus, WorkflowStatus.id == other.status_id)
        .outerjoin(assignee, assignee.id == other.assignee_id)
        .join(creator, creator.id == TaskLink.created_by)
        .order_by(TaskLink.link_type, TaskLink.created_at)
    )
    if not include_archived:
        query = query.where(other.archived_at.is_(None))
    result = []
    for link, linked, status, owner, author in (await session.execute(query)).all():
        kind = kind_of(link.link_type, link.source_task_id == task.id)
        result.append(
            TaskLinkOut(
                id=link.id,
                kind=kind,
                label=LABELS[kind],
                task=LinkedTask(
                    id=linked.id,
                    key=linked.key,
                    title=linked.title,
                    status=StatusBrief(id=status.id, name=status.name, category=status.category),
                    assignee=_brief(owner) if owner else None,
                ),
                created_by=_brief(author),
                created_at=link.created_at,
            )
        )
    return result


def _history(
    session: AsyncSession,
    actor: User,
    source: Task,
    target: Task,
    link_type: LinkType,
    *,
    added: bool,
) -> None:
    for this, that, is_source in ((source, target, True), (target, source, False)):
        text = f"{LABELS[kind_of(link_type.value, is_source)]} {that.key}"
        change = [None, text] if added else [text, None]
        activity.record(session, this.id, actor.id, "updated", {"link": change})


async def add_link(session: AsyncSession, task: Task, actor: User, data: LinkIn) -> TaskLinkOut:
    if data.task_id == task.id:
        raise _invalid("same_task", "A task cannot be linked to itself.")
    other = await session.get(Task, data.task_id)
    if other is None or other.project_id != task.project_id or other.archived_at is not None:
        raise _invalid("unknown_task", "Pick an active task of the same project.")
    link_type, this_is_source = KINDS[data.kind]
    source, target = (task, other) if this_is_source else (other, task)
    if link_type is LinkType.RELATES_TO and source.id > target.id:
        source, target = target, source  # stored once, whichever side adds it
    duplicate = await session.scalar(
        select(TaskLink.id).where(
            TaskLink.link_type == link_type.value,
            or_(
                (TaskLink.source_task_id == source.id) & (TaskLink.target_task_id == target.id),
                (TaskLink.source_task_id == target.id) & (TaskLink.target_task_id == source.id),
            ),
        )
    )
    if duplicate is not None:
        raise AppError(409, "LINK_EXISTS", "These tasks are already linked this way.")
    if len(await list_links(session, task, include_archived=True)) >= MAX_LINKS:
        raise AppError(409, "TOO_MANY_LINKS", f"A task can have at most {MAX_LINKS} links.")
    link = TaskLink(
        project_id=task.project_id,
        source_task_id=source.id,
        target_task_id=target.id,
        link_type=link_type.value,
        created_by=actor.id,
    )
    session.add(link)
    _history(session, actor, source, target, link_type, added=True)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppError(409, "LINK_EXISTS", "These tasks are already linked this way.") from None
    return next(
        o for o in await list_links(session, task, include_archived=True) if o.id == link.id
    )


async def remove_link(session: AsyncSession, task: Task, actor: User, link_id: uuid.UUID) -> None:
    link = await session.get(TaskLink, link_id)
    if link is None or task.id not in (link.source_task_id, link.target_task_id):
        raise AppError(404, "NOT_FOUND", "Link not found.")
    source = await session.get(Task, link.source_task_id)
    target = await session.get(Task, link.target_task_id)
    assert source is not None and target is not None
    _history(session, actor, source, target, LinkType(link.link_type), added=False)
    await session.delete(link)
    await session.commit()
