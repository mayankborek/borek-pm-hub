"""Task business rules. Routers check permissions; this module checks data and uses the DB."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import StaleDataError

from app.common.enums import MembershipSource, ProjectRole, StatusCategory, TaskPriority
from app.core.errors import AppError
from app.projects.models import Project, ProjectMember
from app.tasks import activity, statuses
from app.tasks.models import Task, WorkflowStatus
from app.tasks.schemas import (
    BoardColumn,
    BoardOut,
    StatusBrief,
    TaskCreate,
    TaskOut,
    TaskSort,
    TaskUpdate,
    UserBrief,
)
from app.users.models import User

BOARD_LIMIT = 1000  # a board is never paginated; this keeps one request bounded

# Fields only a PM may change vs. the ones a developer may change on an own task.
DETAIL_FIELDS = frozenset(
    {
        "title",
        "description",
        "priority",
        "labels",
        "start_date",
        "due_date",
        "estimate",
        "assignee_id",
    }
)
STATUS_FIELDS = frozenset({"status_id", "progress", "blocked_reason"})
_NOT_NULL_FIELDS = ("title", "priority", "labels", "progress", "status_id")

Assignee = aliased(User)
Reporter = aliased(User)


def not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Task not found.")


def version_conflict() -> AppError:
    return AppError(
        409, "VERSION_CONFLICT", "The task was changed by someone else. Reload and try again."
    )


def _invalid(field: str, issue: str, message: str) -> AppError:
    return AppError(
        422,
        "VALIDATION_ERROR",
        "The request is not valid.",
        [{"field": field, "issue": issue, "message": message}],
    )


# --- reading ----------------------------------------------------------------------------------


def _select_rows() -> Select[Any]:
    return (
        select(Task, WorkflowStatus, Project, Assignee, Reporter)
        .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
        .join(Project, Project.id == Task.project_id)
        .outerjoin(Assignee, Assignee.id == Task.assignee_id)
        .join(Reporter, Reporter.id == Task.created_by)
        .execution_options(populate_existing=True)  # never return a stale object after commit
    )


def _brief(user: User) -> UserBrief:
    return UserBrief(id=user.id, name=user.name, email=user.email)


def _to_out(
    task: Task, status: WorkflowStatus, project: Project, assignee: User | None, reporter: User
) -> TaskOut:
    return TaskOut(
        id=task.id,
        key=task.key,
        project_id=task.project_id,
        project_code=project.code,
        project_name=project.name,
        title=task.title,
        description=task.description,
        status=StatusBrief(id=status.id, name=status.name, category=status.category),
        priority=task.priority,
        labels=list(task.labels),
        start_date=task.start_date,
        due_date=task.due_date,
        estimate=task.estimate,
        progress=task.progress,
        assignee=_brief(assignee) if assignee else None,
        reporter=_brief(reporter),
        blocked_reason=task.blocked_reason,
        blocked_at=task.blocked_at,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        archived_at=task.archived_at,
        version=task.version,
    )


async def get_task_out(session: AsyncSession, task_id: uuid.UUID) -> TaskOut:
    row = (await session.execute(_select_rows().where(Task.id == task_id))).first()
    if row is None:
        raise not_found()
    return _to_out(*row)


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise not_found()
    return task


class TaskFilters:
    """The filters shared by the project list, the board and GET /tasks."""

    def __init__(
        self,
        *,
        q: str | None = None,
        status_ids: list[uuid.UUID] | None = None,
        categories: list[StatusCategory] | None = None,
        priorities: list[TaskPriority] | None = None,
        assignee_id: uuid.UUID | None = None,
        unassigned: bool = False,
        label: str | None = None,
        due_before: date | None = None,
        due_after: date | None = None,
        overdue: bool = False,
        project_id: uuid.UUID | None = None,
        include_archived: bool = False,
    ) -> None:
        self.q = q
        self.status_ids = status_ids
        self.categories = categories
        self.priorities = priorities
        self.assignee_id = assignee_id
        self.unassigned = unassigned
        self.label = label
        self.due_before = due_before
        self.due_after = due_after
        self.overdue = overdue
        self.project_id = project_id
        self.include_archived = include_archived

    def conditions(self) -> list[ColumnElement[bool]]:
        found: list[ColumnElement[bool]] = []
        if self.project_id:
            found.append(Task.project_id == self.project_id)
        if not self.include_archived:
            found.append(Task.archived_at.is_(None))
        if self.status_ids:
            found.append(Task.status_id.in_(self.status_ids))
        if self.categories:
            found.append(WorkflowStatus.category.in_([c.value for c in self.categories]))
        if self.priorities:
            found.append(Task.priority.in_([p.value for p in self.priorities]))
        if self.assignee_id:
            found.append(Task.assignee_id == self.assignee_id)
        if self.unassigned:
            found.append(Task.assignee_id.is_(None))
        if self.label:
            found.append(Task.labels.contains([self.label]))
        if self.due_before:
            found.append(Task.due_date < self.due_before)
        if self.due_after:
            found.append(Task.due_date > self.due_after)
        if self.overdue:  # past due and not finished
            found.append(Task.due_date < datetime.now(UTC).date())
            found.append(WorkflowStatus.category != StatusCategory.DONE.value)
        if self.q:
            pattern = f"%{self.q.strip().replace('%', r'\%').replace('_', r'\_')}%"
            found.append(
                or_(Task.title.ilike(pattern, escape="\\"), Task.key.ilike(pattern, escape="\\"))
            )
        return found


_PRIORITY_RANK = case(
    {
        TaskPriority.CRITICAL.value: 0,
        TaskPriority.HIGH.value: 1,
        TaskPriority.MEDIUM.value: 2,
        TaskPriority.LOW.value: 3,
    },
    value=Task.priority,
    else_=4,
)


def _order_by(sort: TaskSort) -> list[Any]:
    descending = sort.startswith("-")
    name = sort.lstrip("-")
    column: Any = _PRIORITY_RANK if name == "priority" else getattr(Task, name)
    primary = column.desc() if descending else column.asc()
    if name == "due_date":
        primary = primary.nulls_last()
    return [primary, Task.created_at.desc(), Task.id]


def scope_for_developer(user: User) -> ColumnElement[bool]:
    """Developers see tasks of the active projects they are members of."""
    return Task.project_id.in_(
        select(ProjectMember.project_id)
        .join(Project, Project.id == ProjectMember.project_id)
        .where(ProjectMember.user_id == user.id, Project.archived_at.is_(None))
    )


async def list_tasks(
    session: AsyncSession,
    filters: TaskFilters,
    *,
    sort: TaskSort,
    page: int,
    page_size: int,
    scope: ColumnElement[bool] | None = None,
) -> tuple[list[TaskOut], int]:
    conditions = filters.conditions()
    if scope is not None:
        conditions.append(scope)
    if filters.project_id is None:
        conditions.append(Project.archived_at.is_(None))  # cross-project lists skip archived ones
    total = (
        await session.scalar(
            select(func.count(Task.id))
            .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
            .join(Project, Project.id == Task.project_id)
            .where(*conditions)
        )
        or 0
    )
    rows = await session.execute(
        _select_rows()
        .where(*conditions)
        .order_by(*_order_by(sort))
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return [_to_out(*row) for row in rows.all()], total


async def board(
    session: AsyncSession, project_id: uuid.UUID, filters: TaskFilters, sort: TaskSort
) -> BoardOut:
    conditions = filters.conditions()
    rows = await session.execute(
        _select_rows().where(*conditions).order_by(*_order_by(sort)).limit(BOARD_LIMIT)
    )
    by_status: dict[uuid.UUID, list[TaskOut]] = {}
    for row in rows.all():
        by_status.setdefault(row[1].id, []).append(_to_out(*row))
    columns = [
        BoardColumn(
            status=status,
            total=len(by_status.get(status.id, [])),
            tasks=by_status.get(status.id, []),
        )
        for status in await statuses.list_statuses(session, project_id)
    ]
    return BoardOut(columns=columns, total=sum(c.total for c in columns))


# --- writing ----------------------------------------------------------------------------------


async def _check_assignee(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """The assignee must be an active user. True means they are not a member of the project yet.

    Assigning a task makes the person a member (see `_add_assignment_member`), so the PM does not
    need a separate "add member" step.
    """
    is_active = await session.scalar(select(User.is_active).where(User.id == user_id))
    if not is_active:
        raise _invalid("assignee_id", "unknown_user", "The assignee must be an active user.")
    member_id = await session.scalar(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
        )
    )
    return member_id is None


def _add_assignment_member(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, actor: User
) -> None:
    session.add(
        ProjectMember(
            project_id=project_id,
            user_id=user_id,
            project_role=ProjectRole.DEVELOPER.value,
            source=MembershipSource.TASK_ASSIGNMENT.value,
            granted_by=actor.id,
        )
    )


def _apply_status(task: Task, status: WorkflowStatus, blocked_reason: str | None) -> None:
    """Set the status and keep completed_at / blocked_* consistent with its category.

    Validates first, so a rejected request changes nothing on the task.
    """
    now = datetime.now(UTC)
    reason = (blocked_reason or "").strip()
    is_blocked = status.category == StatusCategory.BLOCKED.value
    if is_blocked and not reason:
        raise _invalid("blocked_reason", "required", "A reason is required for a blocked status.")
    task.status_id = status.id
    if status.category == StatusCategory.DONE.value:
        task.completed_at = task.completed_at or now
    else:
        task.completed_at = None
    task.blocked_reason = reason if is_blocked else None
    task.blocked_at = (task.blocked_at or now) if is_blocked else None


async def create_task(
    session: AsyncSession, project: Project, user: User, data: TaskCreate, *, is_pm: bool
) -> TaskOut:
    assignee_id = data.assignee_id
    if not is_pm:
        if assignee_id not in (None, user.id):
            raise AppError(403, "FORBIDDEN", "Developers can only assign tasks to themselves.")
        assignee_id = user.id
    new_member = assignee_id is not None and await _check_assignee(session, project.id, assignee_id)

    if data.status_id is not None:
        status = await statuses.get_status(session, project.id, data.status_id)
    else:
        status = await _default_status(session, project.id)

    # Atomic key number. The UPDATE locks the project row until commit, so keys never repeat.
    projects = Project.__table__
    number = await session.scalar(
        update(projects)  # type: ignore[arg-type]
        .where(projects.c.id == project.id)
        .values(task_counter=projects.c.task_counter + 1)
        .returning(projects.c.task_counter)
    )
    task = Task(
        project_id=project.id,
        key=f"{project.code}-{number}",
        title=data.title,
        description=data.description,
        status_id=status.id,
        priority=data.priority.value,
        labels=data.labels,
        start_date=data.start_date,
        due_date=data.due_date,
        estimate=(data.estimate or "").strip() or None,
        progress=data.progress,
        assignee_id=assignee_id,
        created_by=user.id,
    )
    _apply_status(task, status, data.blocked_reason)
    session.add(task)
    try:
        await session.flush()
        if new_member:
            assert assignee_id is not None
            _add_assignment_member(session, project.id, assignee_id, user)
        activity.record(session, task.id, user.id, "created")
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppError(409, "CONFLICT", "The task could not be saved. Try again.") from None
    return await get_task_out(session, task.id)


async def _default_status(session: AsyncSession, project_id: uuid.UUID) -> WorkflowStatus:
    todo = await session.scalar(
        select(WorkflowStatus)
        .where(
            WorkflowStatus.project_id == project_id,
            WorkflowStatus.category == StatusCategory.TODO.value,
        )
        .order_by(WorkflowStatus.position)
        .limit(1)
    )
    if todo is not None:
        return todo
    first = await session.scalar(
        select(WorkflowStatus)
        .where(WorkflowStatus.project_id == project_id)
        .order_by(WorkflowStatus.position)
        .limit(1)
    )
    if first is None:
        raise AppError(409, "NO_STATUSES", "The project has no statuses. Add one first.")
    return first


async def _user_name(session: AsyncSession, user_id: uuid.UUID | None) -> str | None:
    if user_id is None:
        return None
    return await session.scalar(select(User.name).where(User.id == user_id))


async def update_task(session: AsyncSession, task: Task, data: TaskUpdate, actor: User) -> TaskOut:
    if data.version != task.version:
        raise version_conflict()
    changes = data.model_dump(exclude={"version"}, exclude_unset=True)
    for field in _NOT_NULL_FIELDS:
        if field in changes and changes[field] is None:
            raise _invalid(field, "required", f"{field} cannot be empty.")

    start = changes.get("start_date", task.start_date)
    due = changes.get("due_date", task.due_date)
    if start and due and due < start:
        raise _invalid("due_date", "before_start", "due_date must not be before start_date.")
    new_assignee_id = changes.get("assignee_id")
    new_member = new_assignee_id is not None and await _check_assignee(
        session, task.project_id, new_assignee_id
    )

    # Do every lookup and check before touching the task, so a rejected request leaves it as is.
    old_status = await session.get(WorkflowStatus, task.status_id)
    assert old_status is not None
    old_assignee = await _user_name(session, task.assignee_id)
    before = activity.snapshot(task, old_status.name, old_assignee)
    new_assignee = (
        await _user_name(session, changes["assignee_id"])
        if "assignee_id" in changes
        else old_assignee
    )
    new_status: WorkflowStatus | None = None
    if "status_id" in changes or "blocked_reason" in changes:
        if "status_id" in changes:
            new_status = await statuses.get_status(session, task.project_id, changes["status_id"])
        else:
            new_status = await session.get(WorkflowStatus, task.status_id)
            assert new_status is not None
        reason = changes["blocked_reason"] if "blocked_reason" in changes else task.blocked_reason
        _apply_status(task, new_status, reason)
    for field in DETAIL_FIELDS & changes.keys():
        value = changes[field]
        if field == "estimate":
            value = (value or "").strip() or None
        setattr(task, field, value.value if field == "priority" else value)
    if "progress" in changes:
        task.progress = changes["progress"]
    changed = activity.diff(
        before, activity.snapshot(task, (new_status or old_status).name, new_assignee)
    )
    if changed:
        activity.record(session, task.id, actor.id, "updated", changed)
    if new_member:
        assert new_assignee_id is not None
        _add_assignment_member(session, task.project_id, new_assignee_id, actor)

    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise version_conflict() from None
    return await get_task_out(session, task.id)


async def assign_task(
    session: AsyncSession, task: Task, assignee_id: uuid.UUID | None, version: int, actor: User
) -> TaskOut:
    """Assign, reassign or (with None) unassign. An assignee who is not a member is added."""
    if version != task.version:
        raise version_conflict()
    new_member = assignee_id is not None and await _check_assignee(
        session, task.project_id, assignee_id
    )
    if assignee_id != task.assignee_id:  # same assignee: nothing to save, version stays
        names = [
            await _user_name(session, task.assignee_id),
            await _user_name(session, assignee_id),
        ]
        activity.record(session, task.id, actor.id, "updated", {"assignee": names})
        task.assignee_id = assignee_id
        if new_member:
            assert assignee_id is not None
            _add_assignment_member(session, task.project_id, assignee_id, actor)
        try:
            await session.commit()
        except StaleDataError:
            await session.rollback()
            raise version_conflict() from None
    return await get_task_out(session, task.id)


async def archive_task(session: AsyncSession, task: Task, actor: User) -> None:
    """Soft delete: hidden from lists, data kept. Archiving twice is harmless."""
    if task.archived_at is None:
        task.archived_at = datetime.now(UTC)
        activity.record(session, task.id, actor.id, "archived")
        await session.commit()
