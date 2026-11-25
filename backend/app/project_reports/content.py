"""Build the snapshot of a report from the project's current data (one function per type)."""

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.change_requests.models import ChangeRequest
from app.common.enums import StatusCategory
from app.manager.next_action import NextActionKind, next_actions
from app.milestones import service as roadmap
from app.project_reports.models import PeriodKind, ReportKind
from app.project_reports.schemas import (
    DistributionItem,
    Fact,
    Kpi,
    ReportContent,
    Table,
)
from app.projects.models import Project, ProjectMember
from app.reporting.models import StatusReport
from app.reporting.service import latest_published
from app.tasks.models import Task, WorkflowStatus
from app.tasks.stats import task_stats
from app.users.models import User

MAX_ROWS = 2000  # a report is built in memory; the table says how many rows there were

DEFAULT_TITLES = {
    ReportKind.TASKS: "Task report",
    ReportKind.MILESTONES: "Milestone report",
    ReportKind.CHANGE_REQUESTS: "Change request report",
    ReportKind.OTHER: "Custom report",
}
MILESTONE_STATE = {
    "done": "Done",
    "late": "Late",
    "revised": "Revised",
    "at_risk": "At risk",
    "in_progress": "In progress",
    "planned": "Planned",
}
CR_STATUS = {
    "pending": "Pending",
    "in_review": "In review",
    "approved": "Accepted",
    "declined": "Declined",
}
PROJECT_STATUS = {
    "planned": "Planned",
    "active": "In progress",
    "on_hold": "On hold",
    "completed": "Completed",
    "cancelled": "Cancelled",
}
HEALTH = {"green": "On track", "amber": "At risk", "red": "Off track"}
NEXT_ACTION = {
    NextActionKind.OVERDUE_MILESTONE: "Overdue milestone",
    NextActionKind.CHANGE_REQUEST: "Decide change request",
    NextActionKind.CLIENT_ACCEPTANCE: "Waiting for client acceptance",
    NextActionKind.NEXT_MILESTONE: "Next milestone",
}


def default_title(kind: ReportKind, period_kind: PeriodKind) -> str:
    if kind == ReportKind.PROJECT_STATUS:
        return (
            "Weekly project status report"
            if period_kind == PeriodKind.WEEKLY
            else "Project status report"
        )
    return DEFAULT_TITLES[kind]


def _start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _after(day: date) -> datetime:
    """Midnight after `day` (UTC): timestamps before it fall on or before that day."""
    return _start(day + timedelta(days=1))


def _iso(value: date | None) -> str:
    return value.isoformat() if value else ""


def _percent(part: int, whole: int) -> str:
    return f"{part * 100 // whole}%" if whole else "-"


def _cut(rows: list[list[str]]) -> tuple[list[list[str]], int]:
    return rows[:MAX_ROWS], len(rows)


def impact_text(value: int | None, unit: str | None) -> str:
    if value is None or unit is None:
        return ""
    name = unit[:-1] if abs(value) == 1 else unit  # 1 day, 3 days
    return f"{value:+d} {name}"


# --- tasks ------------------------------------------------------------------------------------


async def tasks_content(
    session: AsyncSession, project_id: uuid.UUID, start: date, end: date
) -> ReportContent:
    """Every active task that existed by the end of the period and was not finished before it
    started. Status is the current one; completed = in a done status now."""
    assignee = User
    statuses = list(
        await session.scalars(
            select(WorkflowStatus)
            .where(WorkflowStatus.project_id == project_id)
            .order_by(WorkflowStatus.position)
        )
    )
    rows = (
        await session.execute(
            select(Task, WorkflowStatus, assignee)
            .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
            .outerjoin(assignee, assignee.id == Task.assignee_id)
            .where(
                Task.project_id == project_id,
                Task.archived_at.is_(None),
                Task.created_at < _after(end),
                or_(Task.completed_at.is_(None), Task.completed_at >= _start(start)),
            )
            .order_by(WorkflowStatus.position, Task.created_at, Task.key)
        )
    ).all()
    counts: dict[uuid.UUID, int] = {}
    completed = 0
    table: list[list[str]] = []
    for task, status, person in rows:
        counts[status.id] = counts.get(status.id, 0) + 1
        if status.category == StatusCategory.DONE.value:
            completed += 1
        table.append(
            [
                f"{task.key} · {task.title}",
                status.name,
                person.name if person else "Unassigned",
                _iso(task.due_date),
            ]
        )
    total = len(rows)
    shown, all_rows = _cut(table)
    return ReportContent(
        kpis=[
            Kpi(key="total", label="Tasks in snapshot", value=str(total)),
            Kpi(key="completed", label="Completed", value=str(completed)),
            Kpi(key="remaining", label="Remaining", value=str(total - completed)),
            Kpi(key="completion", label="Completion", value=_percent(completed, total)),
        ],
        distribution=[
            DistributionItem(label=s.name, category=s.category, count=counts.get(s.id, 0))
            for s in statuses
        ],
        tables=[
            Table(
                key="tasks",
                heading="Task detail",
                columns=["Task", "Status", "Assignee", "Due"],
                rows=shown,
                total_rows=all_rows,
            )
        ],
    )


# --- milestones -------------------------------------------------------------------------------


async def milestones_content(
    session: AsyncSession, project_id: uuid.UUID, start: date, end: date
) -> ReportContent:
    """Milestones whose baseline or current due date is in the period, or reached in it.
    Baseline = the date before an approved change moved it; forecast = the current date."""
    found = []
    for m in await roadmap.milestones_out(
        session, await roadmap.active_milestones(session, [project_id])
    ):
        baseline = m.original_due_date or m.due_date
        reached = m.completed_at.date() if m.completed_at else None
        if (
            start <= m.due_date <= end
            or start <= baseline <= end
            or (reached is not None and start <= reached <= end)
        ):
            found.append((m, baseline, reached))
    done = sum(1 for m, _, _ in found if m.state.value == "done")
    late = sum(1 for m, _, _ in found if m.state.value == "late")
    moved = sum(1 for m, baseline, _ in found if baseline != m.due_date)
    rows = [
        [
            f"{m.code} · {m.name}",
            MILESTONE_STATE.get(m.state.value, m.state.value),
            _iso(baseline),
            _iso(m.due_date),
            _iso(reached),
        ]
        for m, baseline, reached in found
    ]
    shown, all_rows = _cut(rows)
    return ReportContent(
        kpis=[
            Kpi(key="total", label="Milestones", value=str(len(found))),
            Kpi(key="done", label="Done", value=str(done)),
            Kpi(key="late", label="Late", value=str(late)),
            Kpi(key="moved", label="Moved", value=str(moved)),
        ],
        tables=[
            Table(
                key="milestones",
                heading="Milestones",
                columns=["Milestone", "Status", "Baseline", "Forecast", "Reached"],
                rows=shown,
                total_rows=all_rows,
            )
        ],
    )


# --- change requests --------------------------------------------------------------------------


async def change_requests_content(
    session: AsyncSession, project_id: uuid.UUID, start: date, end: date
) -> ReportContent:
    """Requests raised or decided in the period. Effort stays out (internal); the schedule
    impact is the one the client sees too."""
    in_period = and_(
        ChangeRequest.created_at >= _start(start), ChangeRequest.created_at < _after(end)
    )
    decided = and_(
        ChangeRequest.decided_at >= _start(start), ChangeRequest.decided_at < _after(end)
    )
    found = list(
        await session.scalars(
            select(ChangeRequest)
            .where(ChangeRequest.project_id == project_id, or_(in_period, decided))
            .order_by(ChangeRequest.created_at, ChangeRequest.code)
        )
    )
    by_status: dict[str, int] = {}
    for r in found:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    rows = [
        [
            f"{r.code} · {r.title}",
            CR_STATUS.get(r.status, r.status),
            impact_text(r.impact_schedule_value, r.impact_schedule_unit),
            r.created_at.date().isoformat(),
            r.decided_at.date().isoformat() if r.decided_at else "",
        ]
        for r in found
    ]
    shown, all_rows = _cut(rows)
    return ReportContent(
        kpis=[
            Kpi(key="total", label="Change requests", value=str(len(found))),
            Kpi(
                key="open",
                label="Open",
                value=str(by_status.get("pending", 0) + by_status.get("in_review", 0)),
            ),
            Kpi(key="approved", label="Accepted", value=str(by_status.get("approved", 0))),
            Kpi(key="declined", label="Declined", value=str(by_status.get("declined", 0))),
        ],
        tables=[
            Table(
                key="change_requests",
                heading="Change requests",
                columns=["Request", "Status", "Proposed impact", "Raised", "Decided"],
                rows=shown,
                total_rows=all_rows,
            )
        ],
    )


# --- project status ---------------------------------------------------------------------------


async def project_status_content(
    session: AsyncSession, project: Project, start: date | None, end: date | None
) -> ReportContent:
    """Status, health (newest published status report), target date, project leads and the
    next action, plus the task figures. Weekly adds what was completed and due that week."""
    stats = await task_stats(session, project.id)
    health_row = (
        await session.execute(latest_published().where(StatusReport.project_id == project.id))
    ).first()
    leads = list(
        await session.scalars(
            select(User.name)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(
                ProjectMember.project_id == project.id,
                ProjectMember.project_role == "project_lead",
            )
            .order_by(User.name)
        )
    )
    action = (await next_actions(session, [project.id], change_requests_for=[project.id])).get(
        project.id
    )
    facts = [
        Fact(key="status", label="Project status", value=PROJECT_STATUS.get(project.status, "")),
        Fact(
            key="health",
            label="Health",
            value=HEALTH.get(health_row[1], "") if health_row else "Not reported yet",
        ),
        Fact(key="target", label="Project target", value=_iso(project.target_end_date)),
        Fact(key="pm", label="Project manager", value=", ".join(leads)),
        Fact(
            key="next_action",
            label="Next action",
            value=f"{NEXT_ACTION[action.kind]}: {action.code} {action.title}" if action else "",
        ),
    ]
    kpis = [
        Kpi(
            key="completion",
            label="Completion",
            value=f"{stats.progress_percent}%" if stats.progress_percent is not None else "-",
        ),
        Kpi(key="open", label="Open tasks", value=str(stats.open)),
        Kpi(key="blocked", label="Blocked", value=str(stats.blocked)),
        Kpi(key="overdue", label="Overdue", value=str(stats.overdue)),
    ]
    if start is not None and end is not None:
        completed_in_week = await session.scalar(
            select(func.count(Task.id)).where(
                Task.project_id == project.id,
                Task.archived_at.is_(None),
                Task.completed_at >= _start(start),
                Task.completed_at < _after(end),
            )
        )
        kpis.append(
            Kpi(
                key="completed_in_period",
                label="Completed this week",
                value=str(completed_in_week or 0),
            )
        )
    return ReportContent(
        kpis=kpis,
        distribution=[
            DistributionItem(label=c.status.name, category=c.status.category, count=c.count)
            for c in stats.by_status
        ],
        facts=facts,
    )


async def build(
    session: AsyncSession,
    project: Project,
    kind: ReportKind,
    start: date | None,
    end: date | None,
) -> ReportContent:
    if kind == ReportKind.OTHER:
        return ReportContent()
    if kind == ReportKind.PROJECT_STATUS:
        return await project_status_content(session, project, start, end)
    assert start is not None and end is not None
    if kind == ReportKind.TASKS:
        return await tasks_content(session, project.id, start, end)
    if kind == ReportKind.MILESTONES:
        return await milestones_content(session, project.id, start, end)
    return await change_requests_content(session, project.id, start, end)
