"""Team capacity and workload (Manager Role Guide, section 8 and Capacity 1-7).

Capacity: a reservation's weekly hours are spread evenly over the person's working days and
counted only on the dates it covers (inclusive). Available hours are the scheduled hours on the
same dates. Percentages are reserved / available x 100, classified on the unrounded total:
below 80 available, 80-100 near capacity, above 100 overallocated; no available hours =
unavailable, or conflict when something is booked anyway. Workload never feeds capacity.

Workload: open tasks (not done) of active projects per assignee, overdue ones, and the
estimates of open tasks in person-days (the workspace day length).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.auth.permissions import works_on_tasks_condition
from app.capacity.models import (
    DEFAULT_WEEKLY_HOURS,
    DEFAULT_WORKING_DAYS,
    Reservation,
    UserSchedule,
    WorkspaceSchedule,
)
from app.capacity.schemas import (
    CapacityOut,
    CapacityStatus,
    CapacitySummary,
    PersonCapacity,
    PersonRef,
    ProjectRef,
    ProjectShare,
    ReservationCreate,
    ReservationOut,
    ReservationUpdate,
    ScheduleIn,
    ScheduleOut,
    Segment,
    WeekOut,
    WorkloadCounts,
    WorkloadOut,
    WorkloadPerson,
    WorkloadProject,
    WorkloadSummary,
)
from app.common.enums import EstimateUnit, ProjectStatus, StatusCategory
from app.core.errors import AppError
from app.organisations.models import Organisation
from app.projects.models import Project, ProjectMember
from app.tasks.models import Task, WorkflowStatus
from app.users.models import User

TIMEZONE = "UTC"
NEAR = 80.0
OVER = 100.0
LOOKAHEAD_DAYS = 366
CLOSED_PROJECTS = (ProjectStatus.COMPLETED.value, ProjectStatus.CANCELLED.value)


def today() -> date:
    return datetime.now(UTC).date()


def _invalid(field: str, issue: str, message: str) -> AppError:
    return AppError(
        422,
        "VALIDATION_ERROR",
        "The request is not valid.",
        [{"field": field, "issue": issue, "message": message}],
    )


def _person(user: User) -> PersonRef:
    return PersonRef(id=user.id, name=user.name, job_title=user.job_title)


def _project(project: Project) -> ProjectRef:
    return ProjectRef(id=project.id, code=project.code, name=project.name)


# --- schedules ----------------------------------------------------------------------------------


def _schedule(hours: float, days: list[int], source: str) -> ScheduleOut:
    return ScheduleOut(
        weekly_hours=hours,
        working_days=sorted(days),
        hours_per_day=round(hours / len(days), 4) if days else 0.0,
        source=source,
    )


async def workspace_schedule(session: AsyncSession) -> ScheduleOut:
    row = await session.get(WorkspaceSchedule, 1)
    if row is None:  # the migration seeds it; fall back to the same default
        return _schedule(float(DEFAULT_WEEKLY_HOURS), DEFAULT_WORKING_DAYS, "workspace")
    return _schedule(float(row.weekly_hours), list(row.working_days), "workspace")


async def schedules_for(
    session: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ScheduleOut]:
    default = await workspace_schedule(session)
    own = (
        {
            s.user_id: s
            for s in await session.scalars(
                select(UserSchedule).where(UserSchedule.user_id.in_(user_ids))
            )
        }
        if user_ids
        else {}
    )
    return {
        uid: (
            _schedule(float(own[uid].weekly_hours), list(own[uid].working_days), "personal")
            if uid in own
            else default
        )
        for uid in user_ids
    }


async def set_workspace_schedule(
    session: AsyncSession, actor: User, data: ScheduleIn
) -> ScheduleOut:
    row = await session.get(WorkspaceSchedule, 1)
    if row is None:
        row = WorkspaceSchedule(id=1, weekly_hours=0, working_days=[1])
        session.add(row)
    row.weekly_hours = data.weekly_hours  # type: ignore[assignment]
    row.working_days = data.working_days
    row.updated_at = datetime.now(UTC)
    record_audit(
        session,
        actor,
        "schedule.workspace_changed",
        "schedule",
        uuid.UUID(int=1),
        after={"weekly_hours": data.weekly_hours, "working_days": data.working_days},
    )
    await session.commit()
    return await workspace_schedule(session)


async def _staff_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.scalar(select(User).where(User.id == user_id, works_on_tasks_condition()))
    if user is None:
        raise AppError(404, "NOT_FOUND", "Person not found.")
    return user


async def get_personal_schedule(session: AsyncSession, user_id: uuid.UUID) -> ScheduleOut:
    await _staff_user(session, user_id)
    return (await schedules_for(session, [user_id]))[user_id]


async def set_personal_schedule(
    session: AsyncSession, actor: User, user_id: uuid.UUID, data: ScheduleIn
) -> ScheduleOut:
    await _staff_user(session, user_id)
    row = await session.get(UserSchedule, user_id)
    if row is None:
        row = UserSchedule(user_id=user_id, weekly_hours=0, working_days=[1], updated_by=actor.id)
        session.add(row)
    row.weekly_hours = data.weekly_hours  # type: ignore[assignment]
    row.working_days = data.working_days
    row.updated_by = actor.id
    row.updated_at = datetime.now(UTC)
    record_audit(
        session,
        actor,
        "schedule.personal_changed",
        "user",
        user_id,
        after={"weekly_hours": data.weekly_hours, "working_days": data.working_days},
    )
    await session.commit()
    return (await schedules_for(session, [user_id]))[user_id]


async def clear_personal_schedule(
    session: AsyncSession, actor: User, user_id: uuid.UUID
) -> ScheduleOut:
    """Back to the workspace default."""
    await _staff_user(session, user_id)
    row = await session.get(UserSchedule, user_id)
    if row is not None:
        await session.delete(row)
        record_audit(session, actor, "schedule.personal_cleared", "user", user_id)
        await session.commit()
    return (await schedules_for(session, [user_id]))[user_id]


# --- reservations -------------------------------------------------------------------------------


async def reservations_out(session: AsyncSession, rows: list[Reservation]) -> list[ReservationOut]:
    users = (
        {
            u.id: u
            for u in await session.scalars(
                select(User).where(User.id.in_({r.user_id for r in rows}))
            )
        }
        if rows
        else {}
    )
    projects = (
        {
            p.id: p
            for p in await session.scalars(
                select(Project).where(Project.id.in_({r.project_id for r in rows}))
            )
        }
        if rows
        else {}
    )
    return [
        ReservationOut(
            id=r.id,
            person=_person(users[r.user_id]),
            project=_project(projects[r.project_id]),
            start_date=r.start_date,
            end_date=r.end_date,
            hours_per_week=float(r.hours_per_week),
            note=r.note,
            version=r.version,
        )
        for r in rows
    ]


async def list_reservations(session: AsyncSession, project_id: uuid.UUID) -> list[Reservation]:
    return list(
        await session.scalars(
            select(Reservation)
            .where(Reservation.project_id == project_id, Reservation.archived_at.is_(None))
            .order_by(Reservation.start_date, Reservation.id)
        )
    )


async def get_reservation(
    session: AsyncSession, project_id: uuid.UUID, reservation_id: uuid.UUID
) -> Reservation:
    found = await session.get(Reservation, reservation_id)
    if found is None or found.project_id != project_id or found.archived_at is not None:
        raise AppError(404, "NOT_FOUND", "Reservation not found.")
    return found


async def create_reservation(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: ReservationCreate
) -> Reservation:
    member = await session.scalar(
        select(ProjectMember.id)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == data.user_id,
            User.is_active.is_(True),
        )
    )
    if member is None:
        raise _invalid("user_id", "not_a_member", "Reserve time only for active project members.")
    row = Reservation(
        user_id=data.user_id,
        project_id=project_id,
        start_date=data.start_date,
        end_date=data.end_date,
        hours_per_week=data.hours_per_week,
        note=data.note,
        created_by=actor.id,
    )
    session.add(row)
    await session.flush()
    record_audit(
        session,
        actor,
        "reservation.created",
        "reservation",
        row.id,
        project_id=project_id,
        after={
            "user_id": str(data.user_id),
            "start_date": data.start_date.isoformat(),
            "end_date": data.end_date.isoformat(),
            "hours_per_week": data.hours_per_week,
        },
    )
    await session.commit()
    await session.refresh(row)
    return row


async def update_reservation(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    reservation_id: uuid.UUID,
    data: ReservationUpdate,
) -> Reservation:
    row = await get_reservation(session, project_id, reservation_id)
    if data.version != row.version:
        raise AppError(409, "VERSION_CONFLICT", "The reservation was changed by someone else.")
    changes = data.model_dump(exclude={"version"}, exclude_unset=True)
    start = changes.get("start_date", row.start_date)
    end = changes.get("end_date", row.end_date)
    if end < start:
        raise _invalid("end_date", "before_start", "end_date must not be before start_date.")
    for field, value in changes.items():
        setattr(row, field, value)
    record_audit(
        session,
        actor,
        "reservation.updated",
        "reservation",
        row.id,
        project_id=project_id,
        after={"changed": sorted(changes)},
    )
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise AppError(
            409, "VERSION_CONFLICT", "The reservation was changed by someone else."
        ) from None
    await session.refresh(row)
    return row


async def archive_reservation(
    session: AsyncSession, actor: User, project_id: uuid.UUID, reservation_id: uuid.UUID
) -> None:
    row = await get_reservation(session, project_id, reservation_id)
    row.archived_at = datetime.now(UTC)
    record_audit(
        session, actor, "reservation.archived", "reservation", row.id, project_id=project_id
    )
    await session.commit()


# --- capacity -----------------------------------------------------------------------------------


def status_of(available: float, reserved: float) -> tuple[float | None, CapacityStatus]:
    if available <= 0:
        return None, "conflict" if reserved > 0 else "unavailable"
    percent = reserved / available * 100
    if percent < NEAR:
        return percent, "available"
    if percent <= OVER:
        return percent, "near_capacity"
    return percent, "overallocated"


def _round(percent: float | None) -> float | None:
    """For display only: the status is always decided on the unrounded value."""
    return None if percent is None else round(percent, 2)


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    for last in (31, 30, 29, 28):
        try:
            return date(year, month, min(day.day, last))
        except ValueError:
            continue
    raise AssertionError("unreachable")


@dataclass
class _Booking:
    project_id: uuid.UUID
    start: date
    end: date
    per_day: float  # weekly hours spread over the person's working days


class _Plan:
    """One person's schedule and bookings, answering per-day questions."""

    def __init__(self, schedule: ScheduleOut, bookings: list[_Booking]) -> None:
        self.days = set(schedule.working_days)
        self.per_day = schedule.hours_per_day
        self.bookings = bookings

    def working(self, day: date) -> bool:
        return day.isoweekday() in self.days

    def available(self, day: date) -> float:
        return self.per_day if self.working(day) else 0.0

    def reserved(self, day: date) -> dict[uuid.UUID, float]:
        out: dict[uuid.UUID, float] = defaultdict(float)
        if self.working(day):
            for b in self.bookings:
                if b.start <= day <= b.end:
                    out[b.project_id] += b.per_day
        return out

    def free(self, day: date) -> bool:
        """A fully unbooked working day with scheduled hours."""
        return self.working(day) and self.per_day > 0 and not self.reserved(day)


def _shares(
    reserved: dict[uuid.UUID, float], available: float, projects: dict[uuid.UUID, Project]
) -> list[ProjectShare]:
    return [
        ProjectShare(
            project=_project(projects[pid]),
            reserved_hours=round(hours, 2),
            percent=_round(hours / available * 100) if available > 0 else None,
        )
        for pid, hours in sorted(reserved.items(), key=lambda kv: projects[kv[0]].code)
    ]


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _segments(
    plan: _Plan, start: date, end: date, projects: dict[uuid.UUID, Project]
) -> list[Segment]:
    """Working days with bookings, merged while bookings and availability stay the same."""
    out: list[Segment] = []
    current: tuple[float, tuple[tuple[uuid.UUID, float], ...]] | None = None
    first = last = start
    totals: tuple[float, dict[uuid.UUID, float]] = (0.0, {})
    count = 0

    def close() -> None:
        if current is None or not current[1]:
            return
        available = totals[0]
        reserved = sum(totals[1].values())
        percent, status = status_of(available, reserved)
        out.append(
            Segment(
                start=first,
                end=last,
                available_hours=round(available, 2),
                reserved_hours=round(reserved, 2),
                total_percent=_round(percent),
                capacity_left=round(available - reserved, 2),
                status=status,
                projects=_shares(totals[1], available, projects),
            )
        )

    for day in _days(start, end):
        if not plan.working(day):
            continue
        reserved = plan.reserved(day)
        key = (plan.available(day), tuple(sorted((k, round(v, 6)) for k, v in reserved.items())))
        if key != current:
            close()
            current, first, count = key, day, 0
            totals = (0.0, defaultdict(float))
        last = day
        count += 1
        totals = (totals[0] + plan.available(day), totals[1])
        for pid, hours in reserved.items():
            totals[1][pid] += hours
    close()
    return out


def _weeks(
    plan: _Plan, start: date, end: date, projects: dict[uuid.UUID, Project]
) -> list[WeekOut]:
    out = []
    week = start - timedelta(days=start.weekday())
    while week <= end:
        available = 0.0
        reserved: dict[uuid.UUID, float] = defaultdict(float)
        for day in _days(max(week, start), min(week + timedelta(days=6), end)):
            available += plan.available(day)
            for pid, hours in plan.reserved(day).items():
                reserved[pid] += hours
        total = sum(reserved.values())
        percent, status = status_of(available, total)
        out.append(
            WeekOut(
                week_start=week,
                available_hours=round(available, 2),
                reserved_hours=round(total, 2),
                total_percent=_round(percent),
                capacity_left=round(available - total, 2),
                status=status,
                projects=_shares(reserved, available, projects),
            )
        )
        week += timedelta(days=7)
    return out


async def capacity(session: AsyncSession, start: date, weeks: int) -> CapacityOut:
    now = today()
    end = start + timedelta(days=7 * weeks - 1)
    horizon_end = max(end, now + timedelta(days=LOOKAHEAD_DAYS))
    horizon_start = min(start, now)
    people = list(
        await session.scalars(
            select(User)
            .where(works_on_tasks_condition(), User.is_active.is_(True))
            .order_by(User.name, User.id)
        )
    )
    schedules = await schedules_for(session, [u.id for u in people])
    rows = list(
        await session.scalars(
            select(Reservation)
            .join(Project, Project.id == Reservation.project_id)
            .where(
                Reservation.archived_at.is_(None),
                Project.archived_at.is_(None),
                Reservation.user_id.in_([u.id for u in people]),
                Reservation.end_date >= horizon_start,
                Reservation.start_date <= horizon_end,
            )
        )
    )
    projects = (
        {
            p.id: p
            for p in await session.scalars(
                select(Project).where(Project.id.in_({r.project_id for r in rows}))
            )
        }
        if rows
        else {}
    )
    by_person: dict[uuid.UUID, list[Reservation]] = defaultdict(list)
    for r in rows:
        by_person[r.user_id].append(r)
    three_months = add_months(now, 3)
    out: list[PersonCapacity] = []
    within: list[bool] = []  # free on some working day in the next 3 months, per person
    for user in people:
        schedule = schedules[user.id]
        n_days = len(schedule.working_days)
        plan = _Plan(
            schedule,
            [
                _Booking(r.project_id, r.start_date, r.end_date, float(r.hours_per_week) / n_days)
                for r in by_person[user.id]
            ],
        )
        next_free = next(
            (d for d in _days(now, now + timedelta(days=LOOKAHEAD_DAYS)) if plan.free(d)), None
        )
        free_until = None
        if next_free is not None:
            later = [b.start for b in plan.bookings if b.start > next_free]
            if later:
                free_until = min(later) - timedelta(days=1)
        out.append(
            PersonCapacity(
                person=_person(user),
                schedule=schedule,
                free_today=plan.free(now),
                next_unallocated_day=next_free,
                free_until=free_until,
                has_engagements=any(b.start <= end and b.end >= start for b in plan.bookings),
                segments=_segments(plan, start, end, projects),
                weeks=_weeks(plan, start, end, projects),
            )
        )
        within.append(any(plan.free(d) for d in _days(now, three_months)))
    return CapacityOut(
        today=now,
        timezone=TIMEZONE,
        period_start=start,
        period_end=end,
        thresholds={"near_capacity": NEAR, "overallocated": OVER},
        summary=CapacitySummary(
            free_today=sum(1 for p in out if p.free_today),
            free_within_3_months=sum(within),
            without_engagements=sum(1 for p in out if not p.has_engagements),
        ),
        people=out,
    )


# --- workload -----------------------------------------------------------------------------------


def _hours(value: int, unit: str, days_per_week: int, hours_per_day: float) -> float:
    if unit == EstimateUnit.MINUTES.value:
        return value / 60
    if unit == EstimateUnit.WEEKS.value:
        return value * days_per_week * hours_per_day
    return float(value)


class _Tally:
    def __init__(self) -> None:
        self.open = 0
        self.overdue = 0
        self.hours = 0.0
        self.estimated = 0
        self.unestimated = 0

    def add(self, overdue: bool, hours: float | None) -> None:
        self.open += 1
        self.overdue += int(overdue)
        if hours is None:
            self.unestimated += 1
        else:
            self.estimated += 1
            self.hours += hours

    def pd(self, hours_per_day: float) -> float | None:
        if not self.estimated or hours_per_day <= 0:
            return None
        return round(self.hours / hours_per_day, 1)

    def counts(self, hours_per_day: float) -> dict[str, object]:
        return {
            "open": self.open,
            "overdue": self.overdue,
            "effort_pd": self.pd(hours_per_day),
            "unestimated": self.unestimated,
        }


async def workload(session: AsyncSession) -> WorkloadOut:
    now = today()
    schedule = await workspace_schedule(session)
    hpd = schedule.hours_per_day
    days_per_week = len(schedule.working_days)
    rows = (
        await session.execute(
            select(Task, Project, Organisation.name)
            .join(Project, Project.id == Task.project_id)
            .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
            .outerjoin(Organisation, Organisation.id == Project.client_organisation_id)
            .where(
                Task.archived_at.is_(None),
                Project.archived_at.is_(None),
                Project.status.not_in(CLOSED_PROJECTS),
                WorkflowStatus.category != StatusCategory.DONE.value,
            )
        )
    ).all()
    per_person: dict[uuid.UUID | None, _Tally] = defaultdict(_Tally)
    per_project: dict[tuple[uuid.UUID | None, uuid.UUID], _Tally] = defaultdict(_Tally)
    projects: dict[uuid.UUID, tuple[Project, str | None]] = {}
    for task, project, client in rows:
        projects[project.id] = (project, client)
        hours = (
            _hours(task.estimate_value, task.estimate_unit, days_per_week, hpd)
            if task.estimate_value is not None and task.estimate_unit
            else None
        )
        overdue = task.due_date is not None and task.due_date < now
        per_person[task.assignee_id].add(overdue, hours)
        per_project[(task.assignee_id, project.id)].add(overdue, hours)
    assignees = [uid for uid in per_person if uid is not None]
    users = (
        {u.id: u for u in await session.scalars(select(User).where(User.id.in_(assignees)))}
        if assignees
        else {}
    )

    def project_rows(uid: uuid.UUID | None) -> list[WorkloadProject]:
        items = [
            WorkloadProject(
                project=_project(projects[pid][0]),
                client=projects[pid][1],
                **tally.counts(hpd),
            )
            for (owner, pid), tally in per_project.items()
            if owner == uid
        ]
        return sorted(items, key=lambda p: (-(p.effort_pd or 0), -p.open, p.project.code))

    people = [
        WorkloadPerson(
            person=_person(users[uid]),
            projects=project_rows(uid),
            **per_person[uid].counts(hpd),
        )
        for uid in assignees
    ]
    people.sort(key=lambda p: (p.effort_pd is None, -(p.effort_pd or 0), -p.open, p.person.name))
    total = _Tally()
    for tally in per_person.values():
        total.open += tally.open
        total.overdue += tally.overdue
        total.hours += tally.hours
        total.estimated += tally.estimated
        total.unestimated += tally.unestimated
    busiest = max(people, key=lambda p: (p.open, p.person.name), default=None)
    unassigned = per_person.get(None, _Tally())
    return WorkloadOut(
        today=now,
        hours_per_day=hpd,
        summary=WorkloadSummary(
            people_with_open_work=len(people),
            projects_with_open_work=len(projects),
            open=total.open,
            overdue=total.overdue,
            effort_pd=total.pd(hpd) or 0.0,
            unestimated=total.unestimated,
            most_open=busiest.person if busiest else None,
            most_open_count=busiest.open if busiest else 0,
        ),
        people=people,
        unassigned=WorkloadCounts(**unassigned.counts(hpd)),
        unassigned_projects=project_rows(None),
    )
