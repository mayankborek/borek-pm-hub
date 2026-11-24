"""Sprints: planning, start, completion with spillover, and the sprint history. Routers check
permissions; rules live here.

Rules (Jira-like):
- A project has any number of planned sprints, at most one active sprint, and its completed
  sprints (the history, newest first).
- A task is in at most one sprint; without one it is in the backlog. Tasks go only into planned
  or active sprints.
- Completing the active sprint records every task's outcome (done or spilled). Done tasks stay in
  the completed sprint; unfinished ones move to a planned sprint, a new sprint, or the backlog.
- Completed sprints never change. Planned sprints can be archived (their tasks go back to the
  backlog); active and completed ones cannot.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import Select, case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.common.enums import StatusCategory
from app.core.errors import AppError
from app.organisations.schemas import PersonBrief
from app.projects.models import Project
from app.sprints.models import Sprint, SprintState, SprintTaskOutcome, TaskOutcome
from app.sprints.schemas import (
    MoveTasks,
    SprintBrief,
    SprintComplete,
    SprintCounts,
    SprintCreate,
    SprintDetailOut,
    SprintOut,
    SprintReport,
    SprintStart,
    SprintTaskOut,
    SprintUpdate,
)
from app.tasks import activity
from app.tasks.models import Task, WorkflowStatus
from app.users.models import User

OPEN_STATES = (SprintState.PLANNED.value, SprintState.ACTIVE.value)


def today() -> date:
    return datetime.now(UTC).date()


def _invalid(field: str, issue: str, message: str) -> AppError:
    return AppError(
        422,
        "VALIDATION_ERROR",
        "The request is not valid.",
        [{"field": field, "issue": issue, "message": message}],
    )


def _not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Sprint not found.")


def _version_conflict() -> AppError:
    return AppError(409, "VERSION_CONFLICT", "The sprint was changed by someone else. Reload.")


def _completed() -> AppError:
    return AppError(409, "SPRINT_COMPLETED", "The sprint is completed and cannot change.")


async def _commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise _version_conflict() from None


def _brief(sprint: Sprint) -> SprintBrief:
    return SprintBrief(
        id=sprint.id, number=sprint.number, name=sprint.name, state=SprintState(sprint.state)
    )


# --- reading ------------------------------------------------------------------------------------


async def get_sprint(session: AsyncSession, project_id: uuid.UUID, sprint_id: uuid.UUID) -> Sprint:
    sprint = await session.get(Sprint, sprint_id, populate_existing=True)
    if sprint is None or sprint.project_id != project_id or sprint.archived_at is not None:
        raise _not_found()
    return sprint


async def check_sprint(
    session: AsyncSession, project_id: uuid.UUID, sprint_id: uuid.UUID, field: str = "sprint_id"
) -> Sprint:
    """For putting tasks in: a planned or active sprint of the same project."""
    sprint = await session.get(Sprint, sprint_id)
    if (
        sprint is None
        or sprint.project_id != project_id
        or sprint.archived_at is not None
        or sprint.state not in OPEN_STATES
    ):
        raise _invalid(field, "unknown_sprint", "Pick a planned or active sprint of this project.")
    return sprint


async def sprint_names(session: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = await session.execute(select(Sprint.id, Sprint.name).where(Sprint.id.in_(wanted)))
    return {sid: name for sid, name in rows.all()}


async def list_sprints(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    state: SprintState | None,
    page: int,
    page_size: int,
) -> tuple[list[Sprint], int]:
    """Active first, then planned (by number), then completed (newest first)."""
    where = [Sprint.project_id == project_id, Sprint.archived_at.is_(None)]
    if state is not None:
        where.append(Sprint.state == state.value)
    total = await session.scalar(select(func.count(Sprint.id)).where(*where)) or 0
    rank = case(
        (Sprint.state == SprintState.ACTIVE.value, 0),
        (Sprint.state == SprintState.PLANNED.value, 1),
        else_=2,
    )
    order = case((Sprint.state == SprintState.COMPLETED.value, -Sprint.number), else_=Sprint.number)
    rows = await session.scalars(
        select(Sprint)
        .where(*where)
        .order_by(rank, order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


async def _people(
    session: AsyncSession, ids: set[uuid.UUID | None]
) -> dict[uuid.UUID, PersonBrief]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = await session.scalars(select(User).where(User.id.in_(wanted)))
    return {u.id: PersonBrief(id=u.id, name=u.name, email=u.email) for u in rows}


async def sprints_out(session: AsyncSession, sprints: list[Sprint]) -> list[SprintOut]:
    ids = [s.id for s in sprints]
    counts: dict[uuid.UUID, tuple[int, int]] = {}
    outcomes: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    if ids:
        rows = await session.execute(
            select(
                Task.sprint_id,
                func.count(Task.id),
                func.count(case((WorkflowStatus.category == StatusCategory.DONE.value, 1))),
            )
            .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
            .where(Task.sprint_id.in_(ids), Task.archived_at.is_(None))
            .group_by(Task.sprint_id)
        )
        counts = {sid: (total, done) for sid, total, done in rows.all()}
        for sid, outcome, n in (
            await session.execute(
                select(SprintTaskOutcome.sprint_id, SprintTaskOutcome.outcome, func.count())
                .where(SprintTaskOutcome.sprint_id.in_(ids))
                .group_by(SprintTaskOutcome.sprint_id, SprintTaskOutcome.outcome)
            )
        ).all():
            outcomes[sid][outcome] = n
    people = await _people(
        session, {s.started_by for s in sprints} | {s.completed_by for s in sprints}
    )
    targets = {
        t.id: t
        for t in (
            await session.scalars(
                select(Sprint).where(
                    Sprint.id.in_({s.spilled_to_sprint_id for s in sprints} - {None})
                )
            )
        )
    }
    now = today()
    result = []
    for s in sprints:
        total, done = counts.get(s.id, (0, 0))
        report = None
        if s.state == SprintState.COMPLETED.value:
            target = targets.get(s.spilled_to_sprint_id) if s.spilled_to_sprint_id else None
            report = SprintReport(
                committed=s.committed_count,
                completed=outcomes[s.id][TaskOutcome.DONE.value],
                spilled=outcomes[s.id][TaskOutcome.SPILLED.value],
                spilled_to=_brief(target) if target else None,
            )
        result.append(
            SprintOut(
                id=s.id,
                project_id=s.project_id,
                number=s.number,
                name=s.name,
                goal=s.goal,
                start_date=s.start_date,
                end_date=s.end_date,
                state=SprintState(s.state),
                today=now,
                days_left=(
                    (s.end_date - now).days
                    if s.state == SprintState.ACTIVE.value and s.end_date
                    else None
                ),
                counts=SprintCounts(total=total, done=done, open=total - done),
                report=report,
                started_at=s.started_at,
                started_by=people.get(s.started_by) if s.started_by else None,
                completed_at=s.completed_at,
                completed_by=people.get(s.completed_by) if s.completed_by else None,
                created_at=s.created_at,
                version=s.version,
            )
        )
    return result


async def _times_spilled(session: AsyncSession, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not task_ids:
        return {}
    rows = await session.execute(
        select(SprintTaskOutcome.task_id, func.count())
        .where(
            SprintTaskOutcome.task_id.in_(task_ids),
            SprintTaskOutcome.outcome == TaskOutcome.SPILLED.value,
        )
        .group_by(SprintTaskOutcome.task_id)
    )
    return {tid: n for tid, n in rows.all()}


def _person(user: User | None) -> PersonBrief | None:
    return PersonBrief(id=user.id, name=user.name, email=user.email) if user else None


async def sprint_detail(session: AsyncSession, sprint: Sprint) -> SprintDetailOut:
    base = (await sprints_out(session, [sprint]))[0]
    tasks: list[SprintTaskOut] = []
    if sprint.state == SprintState.COMPLETED.value:
        rows = (
            await session.execute(
                select(SprintTaskOutcome, Task, User)
                .join(Task, Task.id == SprintTaskOutcome.task_id)
                .outerjoin(User, User.id == Task.assignee_id)
                .where(SprintTaskOutcome.sprint_id == sprint.id)
                .order_by(SprintTaskOutcome.outcome, Task.created_at, Task.key)
            )
        ).all()
        spilled = await _times_spilled(session, [task.id for _, task, _ in rows])
        targets = {
            t.id: t
            for t in await session.scalars(
                select(Sprint).where(
                    Sprint.id.in_({o.moved_to_sprint_id for o, _, _ in rows} - {None})
                )
            )
        }
        for outcome, task, assignee in rows:
            target = targets.get(outcome.moved_to_sprint_id) if outcome.moved_to_sprint_id else None
            tasks.append(
                SprintTaskOut(
                    id=task.id,
                    key=task.key,
                    title=task.title,
                    status_name=outcome.status_name,
                    status_category=None,
                    assignee=_person(assignee),
                    outcome=TaskOutcome(outcome.outcome),
                    moved_to=_brief(target) if target else None,
                    times_spilled=spilled.get(task.id, 0),
                )
            )
    else:
        current = (
            await session.execute(
                select(Task, WorkflowStatus, User)
                .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
                .outerjoin(User, User.id == Task.assignee_id)
                .where(Task.sprint_id == sprint.id, Task.archived_at.is_(None))
                .order_by(Task.created_at, Task.key)
            )
        ).all()
        spilled = await _times_spilled(session, [task.id for task, _, _ in current])
        for task, status, assignee in current:
            tasks.append(
                SprintTaskOut(
                    id=task.id,
                    key=task.key,
                    title=task.title,
                    status_name=status.name,
                    status_category=status.category,
                    assignee=_person(assignee),
                    outcome=None,
                    moved_to=None,
                    times_spilled=spilled.get(task.id, 0),
                )
            )
    return SprintDetailOut(**base.model_dump(), tasks=tasks)


# --- writing ------------------------------------------------------------------------------------


async def _new_sprint(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: SprintCreate
) -> Sprint:
    # Lock the project row so two sprints created at once never get the same number.
    code = await session.scalar(
        select(Project.code).where(Project.id == project_id).with_for_update()
    )
    used = await session.scalar(
        select(func.max(Sprint.number)).where(Sprint.project_id == project_id)
    )
    number = (used or 0) + 1
    sprint = Sprint(
        project_id=project_id,
        number=number,
        name=data.name or f"{code} Sprint {number}",
        goal=data.goal,
        start_date=data.start_date,
        end_date=data.end_date,
        created_by=actor.id,
    )
    session.add(sprint)
    await session.flush()
    record_audit(
        session,
        actor,
        "sprint.created",
        "sprint",
        sprint.id,
        project_id=project_id,
        after={"name": sprint.name},
    )
    return sprint


async def create_sprint(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: SprintCreate
) -> Sprint:
    sprint = await _new_sprint(session, actor, project_id, data)
    await session.commit()
    await session.refresh(sprint)
    return sprint


async def update_sprint(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    data: SprintUpdate,
) -> Sprint:
    sprint = await get_sprint(session, project_id, sprint_id)
    if data.version != sprint.version:
        raise _version_conflict()
    if sprint.state == SprintState.COMPLETED.value:
        raise _completed()
    changes = data.model_dump(exclude={"version"}, exclude_unset=True)
    start = changes.get("start_date", sprint.start_date)
    end = changes.get("end_date", sprint.end_date)
    if start and end and end < start:
        raise _invalid("end_date", "before_start", "end_date must not be before start_date.")
    if sprint.state == SprintState.ACTIVE.value and (start is None or end is None):
        raise _invalid(
            "start_date" if start is None else "end_date",
            "required",
            "An active sprint needs a start and an end date.",
        )
    for field, value in changes.items():
        setattr(sprint, field, value)
    record_audit(
        session,
        actor,
        "sprint.updated",
        "sprint",
        sprint.id,
        project_id=project_id,
        after={"changed": sorted(changes)},
    )
    await _commit(session)
    await session.refresh(sprint)
    return sprint


async def start_sprint(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    data: SprintStart,
) -> Sprint:
    sprint = await get_sprint(session, project_id, sprint_id)
    if data.version != sprint.version:
        raise _version_conflict()
    if sprint.state != SprintState.PLANNED.value:
        raise AppError(409, "SPRINT_NOT_PLANNED", "Only a planned sprint can be started.")
    start = data.start_date or sprint.start_date
    end = data.end_date or sprint.end_date
    if start is None or end is None:
        raise _invalid(
            "start_date" if start is None else "end_date",
            "required",
            "Set a start and an end date to start the sprint.",
        )
    if end < start:
        raise _invalid("end_date", "before_start", "end_date must not be before start_date.")
    running = await session.scalar(
        select(Sprint.name).where(
            Sprint.project_id == project_id,
            Sprint.state == SprintState.ACTIVE.value,
            Sprint.archived_at.is_(None),
        )
    )
    if running is not None:
        raise AppError(
            409,
            "SPRINT_ALREADY_ACTIVE",
            f"{running} is still active. Complete it before starting another sprint.",
        )
    sprint.start_date, sprint.end_date = start, end
    if "goal" in data.model_fields_set:
        sprint.goal = data.goal
    sprint.committed_count = (
        await session.scalar(
            select(func.count(Task.id)).where(
                Task.sprint_id == sprint.id, Task.archived_at.is_(None)
            )
        )
        or 0
    )
    sprint.state = SprintState.ACTIVE.value
    sprint.started_at = datetime.now(UTC)
    sprint.started_by = actor.id
    record_audit(
        session,
        actor,
        "sprint.started",
        "sprint",
        sprint.id,
        project_id=project_id,
        after={"name": sprint.name, "tasks": sprint.committed_count},
    )
    try:
        await _commit(session)
    except IntegrityError:  # another sprint was started at the same moment
        await session.rollback()
        raise AppError(
            409, "SPRINT_ALREADY_ACTIVE", "Another sprint was just started. Reload."
        ) from None
    await session.refresh(sprint)
    return sprint


async def complete_sprint(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    data: SprintComplete,
) -> Sprint:
    sprint = await get_sprint(session, project_id, sprint_id)
    if data.version != sprint.version:
        raise _version_conflict()
    if sprint.state != SprintState.ACTIVE.value:
        raise AppError(409, "SPRINT_NOT_ACTIVE", "Only the active sprint can be completed.")
    target: Sprint | None = None
    if data.move_open_tasks_to is not None:
        target = await check_sprint(
            session, project_id, data.move_open_tasks_to, field="move_open_tasks_to"
        )
        if target.id == sprint.id or target.state != SprintState.PLANNED.value:
            raise _invalid(
                "move_open_tasks_to", "not_planned", "Pick a planned sprint of this project."
            )
    elif data.create_next_sprint:
        target = await _new_sprint(session, actor, project_id, SprintCreate())

    rows = (
        await session.execute(
            select(Task, WorkflowStatus)
            .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
            .where(Task.sprint_id == sprint.id, Task.archived_at.is_(None))
            .order_by(Task.created_at)
        )
    ).all()
    for task, status in rows:
        done = status.category == StatusCategory.DONE.value
        session.add(
            SprintTaskOutcome(
                sprint_id=sprint.id,
                task_id=task.id,
                outcome=(TaskOutcome.DONE if done else TaskOutcome.SPILLED).value,
                status_name=status.name,
                moved_to_sprint_id=None if done else (target.id if target else None),
            )
        )
        if not done:
            task.sprint_id = target.id if target else None
            activity.record(
                session,
                task.id,
                actor.id,
                "updated",
                {"sprint": [sprint.name, target.name if target else None]},
            )
    sprint.state = SprintState.COMPLETED.value
    sprint.completed_at = datetime.now(UTC)
    sprint.completed_by = actor.id
    sprint.spilled_to_sprint_id = target.id if target else None
    spilled = sum(1 for _, status in rows if status.category != StatusCategory.DONE.value)
    record_audit(
        session,
        actor,
        "sprint.completed",
        "sprint",
        sprint.id,
        project_id=project_id,
        after={
            "name": sprint.name,
            "completed": len(rows) - spilled,
            "spilled": spilled,
            "spilled_to": target.name if target else "backlog",
        },
    )
    await _commit(session)
    await session.refresh(sprint)
    return sprint


async def archive_sprint(
    session: AsyncSession, actor: User, project_id: uuid.UUID, sprint_id: uuid.UUID
) -> None:
    """Only a planned sprint. Its tasks go back to the backlog. The row stays."""
    sprint = await get_sprint(session, project_id, sprint_id)
    if sprint.state == SprintState.ACTIVE.value:
        raise AppError(
            409, "SPRINT_ACTIVE", "The sprint is active. Complete it instead of removing it."
        )
    if sprint.state == SprintState.COMPLETED.value:
        raise _completed()
    await session.execute(
        update(Task)
        .where(Task.sprint_id == sprint.id)
        .values(sprint_id=None, version=Task.version + 1)
        .execution_options(synchronize_session=False)
    )
    sprint.archived_at = datetime.now(UTC)
    record_audit(
        session,
        actor,
        "sprint.archived",
        "sprint",
        sprint.id,
        project_id=project_id,
        before={"name": sprint.name},
    )
    await _commit(session)


async def move_tasks(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: MoveTasks
) -> int:
    """Returns how many tasks changed sprint (tasks already there are left alone)."""
    target = await check_sprint(session, project_id, data.sprint_id) if data.sprint_id else None
    wanted = set(data.task_ids)
    tasks = list(
        await session.scalars(
            select(Task).where(
                Task.id.in_(wanted), Task.project_id == project_id, Task.archived_at.is_(None)
            )
        )
    )
    if len(tasks) != len(wanted):
        raise _invalid(
            "task_ids", "unknown_task", "Every task must be an active task of this project."
        )
    names = await sprint_names(session, {t.sprint_id for t in tasks})
    moved = 0
    for task in tasks:
        new_id = target.id if target else None
        if task.sprint_id == new_id:
            continue
        old_name = names.get(task.sprint_id) if task.sprint_id else None
        task.sprint_id = new_id
        activity.record(
            session,
            task.id,
            actor.id,
            "updated",
            {"sprint": [old_name, target.name if target else None]},
        )
        moved += 1
    if moved:
        record_audit(
            session,
            actor,
            "sprint.tasks_moved",
            "project",
            project_id,
            project_id=project_id,
            after={"to": target.name if target else "backlog", "tasks": moved},
        )
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise AppError(
            409, "VERSION_CONFLICT", "A task was changed by someone else. Reload and try again."
        ) from None
    return moved


def open_sprint_ids() -> Select[tuple[uuid.UUID]]:
    """Subquery: planned and active sprints (tasks outside them are the backlog)."""
    return select(Sprint.id).where(Sprint.state.in_(OPEN_STATES), Sprint.archived_at.is_(None))
