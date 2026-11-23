"""Phases, milestones and the roadmap. Routers check permissions; rules live here.

Nothing about progress is stored. Phase status, milestone state and both progress values are
worked out on every read from the dates, the "done" mark and the linked tasks, so the roadmap
always matches the task board.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.change_requests.models import ChangeRequest, ChangeRequestStatus
from app.common.enums import StatusCategory
from app.core.errors import AppError
from app.milestones.models import Milestone, ProjectPhase
from app.milestones.schemas import (
    LinkedTaskOut,
    MilestoneCreate,
    MilestoneDetailOut,
    MilestoneOut,
    MilestoneState,
    MilestoneUpdate,
    PhaseCreate,
    PhaseOut,
    PhaseStatus,
    PhaseUpdate,
    RoadmapOut,
    RoadmapPhaseOut,
)
from app.notifications import events as notifications
from app.organisations.schemas import PersonBrief
from app.projects.models import Project, ProjectMember
from app.tasks.models import Task, WorkflowStatus
from app.users.models import User


def today() -> date:
    return datetime.now(UTC).date()


def _invalid(field: str, issue: str, message: str) -> AppError:
    return AppError(
        422,
        "VALIDATION_ERROR",
        "The request is not valid.",
        [{"field": field, "issue": issue, "message": message}],
    )


def _version_conflict(what: str) -> AppError:
    return AppError(409, "VERSION_CONFLICT", f"The {what} was changed by someone else. Reload.")


def _phase_not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Phase not found.")


def _milestone_not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Milestone not found.")


async def _people(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, PersonBrief]:
    if not ids:
        return {}
    rows = await session.scalars(select(User).where(User.id.in_(ids)))
    return {u.id: PersonBrief(id=u.id, name=u.name, email=u.email) for u in rows}


async def _commit(session: AsyncSession, what: str) -> None:
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise _version_conflict(what) from None


# --- computed values ----------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskCounts:
    total: int = 0
    done: int = 0
    started: int = 0  # not in a "to do" status any more (in progress, blocked or done)


async def _task_counts(
    session: AsyncSession, milestone_ids: list[uuid.UUID]
) -> dict[uuid.UUID, TaskCounts]:
    if not milestone_ids:
        return {}
    rows = await session.execute(
        select(
            Task.milestone_id,
            func.count(Task.id),
            func.count(case((WorkflowStatus.category == StatusCategory.DONE.value, 1))),
            func.count(case((WorkflowStatus.category != StatusCategory.TODO.value, 1))),
        )
        .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
        .where(Task.milestone_id.in_(milestone_ids), Task.archived_at.is_(None))
        .group_by(Task.milestone_id)
    )
    return {mid: TaskCounts(total, done, started) for mid, total, done, started in rows.all()}


@dataclass(frozen=True)
class DateChange:
    requested_date: date | None = None
    code: str | None = None


async def _date_changes(
    session: AsyncSession, milestones: list[Milestone]
) -> dict[uuid.UUID, DateChange]:
    """Per milestone: the newest open (pending or in review) request for a new date; else the
    newest approved one."""
    ids = [m.id for m in milestones]
    if not ids:
        return {}
    rows = await session.scalars(
        select(ChangeRequest)
        .where(
            ChangeRequest.milestone_id.in_(ids),
            ChangeRequest.requested_date.is_not(None),
            ChangeRequest.status.in_(
                [
                    ChangeRequestStatus.PENDING.value,
                    ChangeRequestStatus.IN_REVIEW.value,
                    ChangeRequestStatus.APPROVED.value,
                ]
            ),
        )
        .order_by(ChangeRequest.created_at)
    )
    found: dict[uuid.UUID, DateChange] = {}
    for cr in rows:  # oldest first, so newer ones replace older ones
        assert cr.milestone_id is not None
        current = found.get(cr.milestone_id)
        if cr.status != ChangeRequestStatus.APPROVED.value:  # still open
            found[cr.milestone_id] = DateChange(cr.requested_date, cr.code)
        elif current is None or current.requested_date is None:
            found[cr.milestone_id] = DateChange(None, cr.code)
    return found


def milestone_state(
    milestone: Milestone, counts: TaskCounts, phase: ProjectPhase | None, on: date
) -> MilestoneState:
    if milestone.completed_at is not None:
        return MilestoneState.DONE
    if milestone.due_date < on:
        return MilestoneState.LATE
    if milestone.original_due_date is not None:
        return MilestoneState.REVISED
    if milestone.at_risk:
        return MilestoneState.AT_RISK
    if counts.started or (phase is not None and phase.start_date <= on):
        return MilestoneState.IN_PROGRESS
    return MilestoneState.PLANNED


def milestone_progress(milestone: Milestone, counts: TaskCounts) -> int | None:
    if milestone.completed_at is not None:
        return 100
    return round(100 * counts.done / counts.total) if counts.total else None


async def milestones_out(
    session: AsyncSession, milestones: list[Milestone], *, for_client: bool = False
) -> list[MilestoneOut]:
    """With `for_client`, linked tasks are ignored: state and progress follow only what the PM
    does (done, at risk, dates, approved changes), never developers' task changes."""
    counts = {} if for_client else await _task_counts(session, [m.id for m in milestones])
    phase_ids = {m.phase_id for m in milestones if m.phase_id}
    phases = (
        {
            p.id: p
            for p in await session.scalars(
                select(ProjectPhase).where(ProjectPhase.id.in_(phase_ids))
            )
        }
        if phase_ids
        else {}
    )
    people = await _people(
        session,
        {m.owner_id for m in milestones if m.owner_id}
        | {m.completed_by for m in milestones if m.completed_by},
    )
    changes = await _date_changes(session, milestones)
    on = today()
    out = []
    for m in milestones:
        c = counts.get(m.id, TaskCounts())
        out.append(
            MilestoneOut(
                id=m.id,
                project_id=m.project_id,
                phase_id=m.phase_id,
                code=m.code,
                name=m.name,
                description=m.description,
                completion_criteria=m.completion_criteria,
                due_date=m.due_date,
                original_due_date=m.original_due_date,
                requested_date=changes.get(m.id, DateChange()).requested_date,
                change_request_code=changes.get(m.id, DateChange()).code,
                owner=people.get(m.owner_id) if m.owner_id else None,
                state=milestone_state(m, c, phases.get(m.phase_id) if m.phase_id else None, on),
                done=m.completed_at is not None,
                completed_at=m.completed_at,
                completed_by=people.get(m.completed_by) if m.completed_by else None,
                at_risk=m.at_risk,
                client_visible=m.client_visible,
                progress=milestone_progress(m, c),
                tasks_total=c.total,
                tasks_done=c.done,
                version=m.version,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
        )
    return out


def phase_out(
    phase: ProjectPhase, milestones: list[MilestoneOut], *, for_client: bool = False
) -> PhaseOut:
    """`milestones`: the phase's active milestones, already worked out. With `for_client` the
    completed share is only known once the phase is completed (100), else null."""
    on = today()
    total = len(milestones)
    done = sum(1 for m in milestones if m.done)
    tasks_total = sum(m.tasks_total for m in milestones)
    tasks_done = sum(m.tasks_done for m in milestones)
    if total and done == total:
        status = PhaseStatus.COMPLETED
    elif (
        phase.start_date <= on
        or done
        or any(m.state is MilestoneState.IN_PROGRESS or m.tasks_done for m in milestones)
    ):
        status = PhaseStatus.IN_PROGRESS
    else:
        status = PhaseStatus.NOT_STARTED
    progress: int | None
    if status is PhaseStatus.COMPLETED:
        progress = 100
    elif for_client:
        progress = None
    elif tasks_total:
        progress = round(100 * tasks_done / tasks_total)
    else:
        progress = round(100 * done / total) if total else None
    return PhaseOut(
        id=phase.id,
        project_id=phase.project_id,
        name=phase.name,
        description=phase.description,
        start_date=phase.start_date,
        end_date=phase.end_date,
        position=phase.position,
        client_visible=phase.client_visible,
        status=status,
        is_late=phase.end_date < on and status is not PhaseStatus.COMPLETED,
        progress=progress,
        milestones_total=total,
        milestones_done=done,
        version=phase.version,
        created_at=phase.created_at,
        updated_at=phase.updated_at,
    )


# --- reading ------------------------------------------------------------------------------------


async def active_phases(session: AsyncSession, project_id: uuid.UUID) -> list[ProjectPhase]:
    rows = await session.scalars(
        select(ProjectPhase)
        .where(ProjectPhase.project_id == project_id, ProjectPhase.archived_at.is_(None))
        .order_by(ProjectPhase.position, ProjectPhase.start_date, ProjectPhase.id)
    )
    return list(rows)


async def active_milestones(session: AsyncSession, project_ids: list[uuid.UUID]) -> list[Milestone]:
    """By due date, then code."""
    if not project_ids:
        return []
    rows = await session.scalars(
        select(Milestone)
        .where(Milestone.project_id.in_(project_ids), Milestone.archived_at.is_(None))
        .order_by(Milestone.due_date, Milestone.code)
    )
    return list(rows)


async def get_phase(
    session: AsyncSession, project_id: uuid.UUID, phase_id: uuid.UUID
) -> ProjectPhase:
    phase = await session.get(ProjectPhase, phase_id)
    if phase is None or phase.project_id != project_id or phase.archived_at is not None:
        raise _phase_not_found()
    return phase


async def get_milestone(
    session: AsyncSession, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> Milestone:
    milestone = await session.get(Milestone, milestone_id)
    if milestone is None or milestone.project_id != project_id or milestone.archived_at is not None:
        raise _milestone_not_found()
    return milestone


@dataclass
class Roadmap:
    phases: list[tuple[ProjectPhase, PhaseOut, list[MilestoneOut]]]
    unphased: list[MilestoneOut]
    milestones: list[MilestoneOut]  # all, by due date


async def build_roadmap(
    session: AsyncSession, project_id: uuid.UUID, *, for_client: bool = False
) -> Roadmap:
    phases = await active_phases(session, project_id)
    milestones = await milestones_out(
        session, await active_milestones(session, [project_id]), for_client=for_client
    )
    active_ids = {p.id for p in phases}
    by_phase: dict[uuid.UUID, list[MilestoneOut]] = defaultdict(list)
    unphased = []
    for m in milestones:
        if m.phase_id is not None and m.phase_id in active_ids:
            by_phase[m.phase_id].append(m)
        else:
            unphased.append(m)
    return Roadmap(
        phases=[
            (p, phase_out(p, by_phase[p.id], for_client=for_client), by_phase[p.id]) for p in phases
        ],
        unphased=unphased,
        milestones=milestones,
    )


def date_range(project: Project, dates: list[date]) -> tuple[date | None, date | None]:
    """The span a roadmap shows: project dates, phase dates and milestone dates."""
    known = [d for d in (project.start_date, project.target_end_date, *dates) if d]
    return (min(known), max(known)) if known else (None, None)


def _roadmap_dates(roadmap: Roadmap) -> list[date]:
    found = [m.due_date for m in roadmap.milestones]
    for phase, _, _ in roadmap.phases:
        found += [phase.start_date, phase.end_date]
    return found


async def roadmap_out(session: AsyncSession, project: Project) -> RoadmapOut:
    roadmap = await build_roadmap(session, project.id)
    start, end = date_range(project, _roadmap_dates(roadmap))
    return RoadmapOut(
        project_id=project.id,
        today=today(),
        range_start=start,
        range_end=end,
        phases=[
            RoadmapPhaseOut(**out.model_dump(), milestones=ms) for _, out, ms in roadmap.phases
        ],
        unphased_milestones=roadmap.unphased,
    )


async def phase_out_of(session: AsyncSession, phase: ProjectPhase) -> PhaseOut:
    rows = await session.scalars(
        select(Milestone)
        .where(Milestone.phase_id == phase.id, Milestone.archived_at.is_(None))
        .order_by(Milestone.due_date, Milestone.code)
    )
    return phase_out(phase, await milestones_out(session, list(rows)))


async def milestone_detail(session: AsyncSession, milestone: Milestone) -> MilestoneDetailOut:
    base = (await milestones_out(session, [milestone]))[0]
    rows = await session.execute(
        select(Task, WorkflowStatus, User)
        .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
        .outerjoin(User, User.id == Task.assignee_id)
        .where(Task.milestone_id == milestone.id, Task.archived_at.is_(None))
        .order_by(Task.created_at, Task.key)
    )
    return MilestoneDetailOut(
        **base.model_dump(),
        tasks=[
            LinkedTaskOut(
                id=task.id,
                key=task.key,
                title=task.title,
                status_name=status.name,
                status_category=status.category,
                assignee=(
                    PersonBrief(id=assignee.id, name=assignee.name, email=assignee.email)
                    if assignee
                    else None
                ),
                due_date=task.due_date,
            )
            for task, status, assignee in rows.all()
        ],
    )


# --- phases: writing ----------------------------------------------------------------------------


async def create_phase(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: PhaseCreate
) -> ProjectPhase:
    last = await session.scalar(
        select(func.max(ProjectPhase.position)).where(
            ProjectPhase.project_id == project_id, ProjectPhase.archived_at.is_(None)
        )
    )
    phase = ProjectPhase(
        project_id=project_id,
        position=(last or 0) + 1,
        created_by=actor.id,
        **data.model_dump(),
    )
    session.add(phase)
    await session.flush()
    record_audit(
        session,
        actor,
        "phase.created",
        "phase",
        phase.id,
        project_id=project_id,
        after={"name": phase.name},
    )
    await session.commit()
    await session.refresh(phase)
    return phase


async def update_phase(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    phase_id: uuid.UUID,
    data: PhaseUpdate,
) -> ProjectPhase:
    phase = await get_phase(session, project_id, phase_id)
    if data.version != phase.version:
        raise _version_conflict("phase")
    changes = data.model_dump(exclude={"version"}, exclude_unset=True)
    start = changes.get("start_date", phase.start_date)
    end = changes.get("end_date", phase.end_date)
    if end < start:
        raise _invalid("end_date", "before_start", "end_date must not be before start_date.")
    for field, value in changes.items():
        setattr(phase, field, value)
    record_audit(
        session,
        actor,
        "phase.updated",
        "phase",
        phase.id,
        project_id=project_id,
        after={"changed": sorted(changes)},
    )
    await _commit(session, "phase")
    await session.refresh(phase)
    return phase


async def reorder_phases(
    session: AsyncSession, actor: User, project_id: uuid.UUID, phase_ids: list[uuid.UUID]
) -> None:
    phases = await active_phases(session, project_id)
    if len(phase_ids) != len(set(phase_ids)) or set(phase_ids) != {p.id for p in phases}:
        raise _invalid(
            "phase_ids", "not_all_phases", "Send every active phase of the project exactly once."
        )
    by_id = {p.id: p for p in phases}
    for position, phase_id in enumerate(phase_ids, start=1):
        by_id[phase_id].position = position
    record_audit(session, actor, "phase.reordered", "project", project_id, project_id=project_id)
    await _commit(session, "phase")


async def archive_phase(
    session: AsyncSession, actor: User, project_id: uuid.UUID, phase_id: uuid.UUID
) -> None:
    """Only an empty phase: move or archive its milestones first."""
    phase = await get_phase(session, project_id, phase_id)
    in_use = await session.scalar(
        select(func.count(Milestone.id)).where(
            Milestone.phase_id == phase.id, Milestone.archived_at.is_(None)
        )
    )
    if in_use:
        raise AppError(
            409,
            "PHASE_HAS_MILESTONES",
            "The phase still has milestones. Move or archive them first.",
        )
    phase.archived_at = datetime.now(UTC)
    record_audit(
        session,
        actor,
        "phase.archived",
        "phase",
        phase.id,
        project_id=project_id,
        before={"name": phase.name},
    )
    await _commit(session, "phase")


# --- milestones: writing ------------------------------------------------------------------------


async def _check_owner(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    member = await session.scalar(
        select(ProjectMember.id)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            User.is_active.is_(True),
        )
    )
    if member is None:
        raise _invalid("owner_id", "not_a_member", "The owner must be an active project member.")


async def check_milestone(
    session: AsyncSession, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> None:
    """For links from tasks: an active milestone of the same project."""
    found = await session.scalar(
        select(Milestone.id).where(
            Milestone.id == milestone_id,
            Milestone.project_id == project_id,
            Milestone.archived_at.is_(None),
        )
    )
    if found is None:
        raise _invalid(
            "milestone_id", "unknown_milestone", "Pick an active milestone of this project."
        )


async def _check_phase(session: AsyncSession, project_id: uuid.UUID, phase_id: uuid.UUID) -> None:
    phase = await session.get(ProjectPhase, phase_id)
    if phase is None or phase.project_id != project_id or phase.archived_at is not None:
        raise _invalid("phase_id", "unknown_phase", "Pick an active phase of this project.")


async def _next_code(session: AsyncSession, project_id: uuid.UUID) -> str:
    # Lock the project row so two milestones created at once never get the same code.
    await session.execute(select(Project.id).where(Project.id == project_id).with_for_update())
    used = await session.scalar(
        select(func.count(Milestone.id)).where(Milestone.project_id == project_id)
    )
    return f"M-{(used or 0) + 1:02d}"


async def create_milestone(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: MilestoneCreate
) -> Milestone:
    if data.phase_id:
        await _check_phase(session, project_id, data.phase_id)
    if data.owner_id:
        await _check_owner(session, project_id, data.owner_id)
    milestone = Milestone(
        project_id=project_id,
        code=await _next_code(session, project_id),
        created_by=actor.id,
        **data.model_dump(),
    )
    session.add(milestone)
    await session.flush()
    record_audit(
        session,
        actor,
        "milestone.created",
        "milestone",
        milestone.id,
        project_id=project_id,
        after={"code": milestone.code, "name": milestone.name},
    )
    await notifications.milestone_changed(
        session, actor, milestone, was_visible=False, old_due=milestone.due_date, was_done=False
    )
    await session.commit()
    await session.refresh(milestone)
    return milestone


async def update_milestone(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    data: MilestoneUpdate,
) -> Milestone:
    milestone = await get_milestone(session, project_id, milestone_id)
    if data.version != milestone.version:
        raise _version_conflict("milestone")
    changes = data.model_dump(exclude={"version"}, exclude_unset=True)
    if changes.get("phase_id"):
        await _check_phase(session, project_id, changes["phase_id"])
    if changes.get("owner_id"):
        await _check_owner(session, project_id, changes["owner_id"])
    was_visible, old_due = milestone.client_visible, milestone.due_date
    was_done = milestone.completed_at is not None
    done = changes.pop("done", None)
    if done is True and milestone.completed_at is None:
        milestone.completed_at = datetime.now(UTC)
        milestone.completed_by = actor.id
    elif done is False:
        milestone.completed_at = None
        milestone.completed_by = None
    for field, value in changes.items():
        setattr(milestone, field, value)
    after: dict[str, object] = {"changed": sorted(changes)}
    if done is not None:
        after["done"] = done
    record_audit(
        session,
        actor,
        "milestone.updated",
        "milestone",
        milestone.id,
        project_id=project_id,
        after=after,
    )
    await notifications.milestone_changed(
        session, actor, milestone, was_visible=was_visible, old_due=old_due, was_done=was_done
    )
    await _commit(session, "milestone")
    await session.refresh(milestone)
    return milestone


async def archive_milestone(
    session: AsyncSession, actor: User, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> None:
    """Archived, not deleted. Its tasks lose the link (they stay as they are otherwise)."""
    milestone = await get_milestone(session, project_id, milestone_id)
    await session.execute(
        update(Task)
        .where(Task.milestone_id == milestone.id)
        .values(milestone_id=None, version=Task.version + 1)
        .execution_options(synchronize_session=False)
    )
    milestone.archived_at = datetime.now(UTC)
    record_audit(
        session,
        actor,
        "milestone.archived",
        "milestone",
        milestone.id,
        project_id=project_id,
        before={"code": milestone.code, "name": milestone.name},
    )
    await _commit(session, "milestone")
