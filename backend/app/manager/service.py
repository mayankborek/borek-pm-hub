"""Delivery overviews for Managers (all projects) and Account Managers (their clients' projects):
the dashboard, one project's delivery summary, and the extra portfolio card fields. Progress is
always what the PM published, the same figure the client sees."""

import uuid
from datetime import date, timedelta

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import sees_all_projects
from app.change_requests.models import ChangeRequest, ChangeRequestStatus
from app.common.enums import ProjectStatus, ReportState
from app.manager.schemas import (
    DeliveryEvent,
    ManagerDashboardOut,
    ManagerKpis,
    MilestoneCompletion,
    NextMilestone,
    ProjectOverviewOut,
    ProjectRef,
    PublishedProgress,
    TrendPoint,
    UpcomingMilestone,
)
from app.milestones import service as roadmap
from app.milestones.models import Milestone
from app.milestones.schemas import MilestoneOut
from app.projects.membership import oversight_project_ids
from app.projects.models import Project
from app.reporting.models import StatusReport
from app.requirements.models import Requirement, RequirementStatus, RequirementVersion
from app.users.models import User

UPCOMING_DAYS = 14
MAX_EVENTS = 10
CLOSED_STATUSES = (ProjectStatus.COMPLETED.value, ProjectStatus.CANCELLED.value)


def scope(user: User) -> list[ColumnElement[bool]]:
    """Active projects the user oversees: every one for a Manager, else the visible ones."""
    conditions: list[ColumnElement[bool]] = [Project.archived_at.is_(None)]
    if not sees_all_projects(user):
        conditions.append(Project.id.in_(oversight_project_ids(user)))
    return conditions


def _ref(p: Project) -> ProjectRef:
    return ProjectRef(id=p.id, code=p.code, name=p.name)


def _published() -> list[ColumnElement[bool]]:
    return [StatusReport.state == ReportState.PUBLISHED.value, StatusReport.archived_at.is_(None)]


async def published_progress(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, PublishedProgress]:
    """Per project, the newest published report that shares a progress figure."""
    if not project_ids:
        return {}
    rows = (
        await session.execute(
            select(StatusReport, User.name)
            .outerjoin(User, User.id == StatusReport.published_by)
            .where(
                StatusReport.project_id.in_(project_ids),
                StatusReport.progress_percent.is_not(None),
                *_published(),
            )
            .distinct(StatusReport.project_id)
            .order_by(
                StatusReport.project_id,
                StatusReport.report_date.desc(),
                StatusReport.published_at.desc(),
            )
        )
    ).all()
    out = {}
    for report, name in rows:
        assert report.progress_percent is not None
        out[report.project_id] = PublishedProgress(
            percent=report.progress_percent,
            published_on=report.report_date,
            published_by=name,
            report_id=report.id,
        )
    return out


def _next(m: MilestoneOut) -> NextMilestone:
    return NextMilestone(id=m.id, code=m.code, name=m.name, due_date=m.due_date, state=m.state)


async def _open_milestones(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> list[MilestoneOut]:
    """Open milestones by due date, with their staff-side state (late, revised, at risk ...)."""
    open_ones = [
        m for m in await roadmap.active_milestones(session, project_ids) if m.completed_at is None
    ]
    return await roadmap.milestones_out(session, open_ones)


async def next_milestones(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, NextMilestone]:
    out: dict[uuid.UUID, NextMilestone] = {}
    for m in await _open_milestones(session, project_ids):  # by due date: the first one wins
        out.setdefault(m.project_id, _next(m))
    return out


async def _events(session: AsyncSession, projects: dict[uuid.UUID, Project]) -> list[DeliveryEvent]:
    """Reports published, change requests raised / taken into review / decided, milestones
    shared with the client or reached, requirements published and answered. Newest first, at
    most MAX_EVENTS."""
    if not projects:
        return []
    ids = list(projects)
    events: list[DeliveryEvent] = []
    for report in await session.scalars(
        select(StatusReport)
        .where(StatusReport.project_id.in_(ids), *_published())
        .order_by(StatusReport.published_at.desc())
        .limit(MAX_EVENTS)
    ):
        assert report.published_at is not None
        events.append(
            DeliveryEvent(
                kind="report",
                project=_ref(projects[report.project_id]),
                title=f"Status report {report.report_date:%d.%m.%Y}",
                occurred_at=report.published_at,
                entity_id=report.id,
                status=None,
            )
        )
    for cr in await session.scalars(
        select(ChangeRequest)
        .where(ChangeRequest.project_id.in_(ids))
        .order_by(func.coalesce(ChangeRequest.decided_at, ChangeRequest.updated_at).desc())
        .limit(MAX_EVENTS * 3)
    ):
        steps = [(cr.created_at, ChangeRequestStatus.PENDING.value)]
        if cr.review_started_at:
            steps.append((cr.review_started_at, ChangeRequestStatus.IN_REVIEW.value))
        if cr.decided_at:
            steps.append((cr.decided_at, cr.status))
        events += [
            DeliveryEvent(
                kind="change_request",
                project=_ref(projects[cr.project_id]),
                title=f"{cr.code} {cr.title}",
                occurred_at=at,
                entity_id=cr.id,
                status=status,
            )
            for at, status in steps
        ]
    for column, status in ((Milestone.shared_at, "shared"), (Milestone.completed_at, "done")):
        for m in await session.scalars(
            select(Milestone)
            .where(
                Milestone.project_id.in_(ids),
                Milestone.archived_at.is_(None),
                column.is_not(None),
            )
            .order_by(column.desc())
            .limit(MAX_EVENTS)
        ):
            at = m.shared_at if status == "shared" else m.completed_at
            assert at is not None
            events.append(
                DeliveryEvent(
                    kind="milestone",
                    project=_ref(projects[m.project_id]),
                    title=f"{m.code} {m.name}",
                    occurred_at=at,
                    entity_id=m.id,
                    status=status,
                    due_date=m.due_date,
                )
            )
    rows = await session.execute(
        select(Requirement, RequirementVersion)
        .join(RequirementVersion, RequirementVersion.requirement_id == Requirement.id)
        .where(
            Requirement.project_id.in_(ids),
            Requirement.archived_at.is_(None),
            RequirementVersion.published_at.is_not(None),
        )
        .order_by(RequirementVersion.published_at.desc())
        .limit(MAX_EVENTS * 2)
    )
    for req, version in rows.all():
        assert version.published_at is not None
        title = f"{req.code} {req.title} (version {version.number})"
        events.append(
            DeliveryEvent(
                kind="requirement",
                project=_ref(projects[req.project_id]),
                title=title,
                occurred_at=version.published_at,
                entity_id=req.id,
                status=RequirementStatus.AWAITING_ACCEPTANCE.value,
            )
        )
        if version.responded_at and version.response:
            events.append(
                DeliveryEvent(
                    kind="requirement",
                    project=_ref(projects[req.project_id]),
                    title=title,
                    occurred_at=version.responded_at,
                    entity_id=req.id,
                    status=version.response,
                )
            )
    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events[:MAX_EVENTS]


async def _awaiting_client(session: AsyncSession, project_ids: list[uuid.UUID]) -> int:
    if not project_ids:
        return 0
    return (
        await session.scalar(
            select(func.count(Requirement.id)).where(
                Requirement.project_id.in_(project_ids),
                Requirement.archived_at.is_(None),
                Requirement.status == RequirementStatus.AWAITING_ACCEPTANCE.value,
            )
        )
        or 0
    )


async def dashboard(session: AsyncSession, user: User) -> ManagerDashboardOut:
    projects = {p.id: p for p in await session.scalars(select(Project).where(*scope(user)))}
    ids = list(projects)
    live = [pid for pid, p in projects.items() if p.status not in CLOSED_STATUSES]
    today = roadmap.today()
    soon = [
        m
        for m in await _open_milestones(session, live)
        if today <= m.due_date <= today + timedelta(days=UPCOMING_DAYS)
    ]
    cr_counts: dict[str, int] = {}
    if ids:
        cr_counts = {
            status: count
            for status, count in (
                await session.execute(
                    select(ChangeRequest.status, func.count(ChangeRequest.id))
                    .where(ChangeRequest.project_id.in_(ids))
                    .group_by(ChangeRequest.status)
                )
            ).all()
        }
    reports = (
        await session.scalar(
            select(func.count(StatusReport.id)).where(
                StatusReport.project_id.in_(ids), *_published()
            )
        )
        if ids
        else 0
    )
    return ManagerDashboardOut(
        today=today,
        kpis=ManagerKpis(
            active_projects=len(live),
            shared_reports=reports or 0,
            upcoming_milestones=len(soon),
            requests_in_review=cr_counts.get(ChangeRequestStatus.IN_REVIEW.value, 0),
            requests_pending=cr_counts.get(ChangeRequestStatus.PENDING.value, 0),
            awaiting_client=await _awaiting_client(session, ids),
        ),
        upcoming_milestones=[
            UpcomingMilestone(**_next(m).model_dump(), project=_ref(projects[m.project_id]))
            for m in soon
        ],
        updates=await _events(session, projects),
    )


def _days_left(target: date | None, today: date) -> int | None:
    return (target - today).days if target else None


async def project_overview(session: AsyncSession, project: Project) -> ProjectOverviewOut:
    today = roadmap.today()
    milestones = await roadmap.active_milestones(session, [project.id])
    trend_rows = await session.scalars(
        select(StatusReport)
        .where(
            StatusReport.project_id == project.id,
            StatusReport.progress_percent.is_not(None),
            *_published(),
        )
        .order_by(StatusReport.report_date, StatusReport.published_at)
    )
    trend = [
        TrendPoint(report_id=r.id, report_date=r.report_date, percent=r.progress_percent)
        for r in trend_rows
        if r.progress_percent is not None
    ]
    progress = (await published_progress(session, [project.id])).get(project.id)
    return ProjectOverviewOut(
        project=_ref(project),
        today=today,
        target_end_date=project.target_end_date,
        days_left=_days_left(project.target_end_date, today),
        progress=progress,
        progress_trend=trend,
        milestones=MilestoneCompletion(
            done=sum(1 for m in milestones if m.completed_at is not None), total=len(milestones)
        ),
        next_milestone=(await next_milestones(session, [project.id])).get(project.id),
        client_actions=await _awaiting_client(session, [project.id]),
        activity=await _events(session, {project.id: project}),
    )
