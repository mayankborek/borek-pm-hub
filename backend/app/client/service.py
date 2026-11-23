"""Client portal data. One rule decides what a client sees (`_visible`): the external, not archived
projects of the client's own organisation. Only what the PM publishes reaches the client: project
progress comes from published status reports and milestone progress is never task-based here, so
developers' day-to-day task changes stay internal. Tasks, effort, activity, drafts and money
never leave this module."""

import uuid
from collections import Counter
from datetime import timedelta

from fastapi import UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import ColumnElement, and_, false, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.change_requests import service as change_requests
from app.change_requests.models import ChangeRequest, ChangeRequestStatus
from app.change_requests.schemas import AttachmentOut, ChangeRequestCreate, CommentOut
from app.client.schemas import (
    HEALTH_OF_RAG,
    ClientAttachmentOut,
    ClientChangeRequestBrief,
    ClientChangeRequestListOut,
    ClientChangeRequestOut,
    ClientCommentOut,
    ClientContactOut,
    ClientKpis,
    ClientLatestReport,
    ClientMilestoneOut,
    ClientMilestoneRef,
    ClientOrganisationOut,
    ClientPersonOut,
    ClientPhaseOut,
    ClientPortalOut,
    ClientProjectDetailOut,
    ClientProjectOut,
    ClientReportBrief,
    ClientReportOut,
    ClientRoadmapOut,
    ClientUpcomingMilestone,
    ClientUpdateOut,
    LatestUpdate,
    NextMilestone,
    PublishedBy,
)
from app.common.enums import (
    GLOBAL_ROLE_LABELS,
    GlobalRole,
    ProjectRole,
    ProjectStatus,
    ProjectType,
    ReportState,
)
from app.core.errors import AppError
from app.milestones import service as roadmap
from app.milestones.models import Milestone
from app.milestones.schemas import MilestoneOut
from app.organisations.models import Organisation, OrganisationAccountManager
from app.projects.models import Project, ProjectMember
from app.projects.service import ensure_writable
from app.reporting.models import Stakeholder, StatusReport
from app.requirements import service as requirements
from app.requirements.schemas import (
    ClientRequirementListOut,
    ClientRequirementOut,
    ClientRequirementResponse,
)
from app.users.models import User

MAX_UPDATES = 10
UPCOMING_DAYS = 14
CLOSED_PROJECT_STATUSES = (ProjectStatus.COMPLETED.value, ProjectStatus.CANCELLED.value)


def _not_found() -> AppError:
    # The same answer as for a project that does not exist: a client never learns about others.
    return AppError(404, "NOT_FOUND", "Project not found.")


def _visible(user: User) -> ColumnElement[bool]:
    if user.organisation_id is None:
        return false()
    return and_(
        Project.client_organisation_id == user.organisation_id,
        Project.project_type == ProjectType.EXTERNAL.value,
        Project.archived_at.is_(None),
    )


def _published() -> ColumnElement[bool]:
    return and_(
        StatusReport.state == ReportState.PUBLISHED.value, StatusReport.archived_at.is_(None)
    )


def _title(report: StatusReport) -> str:
    return f"Status report {report.report_date:%d.%m.%Y}"


def _role_label(user: User) -> str:
    return GLOBAL_ROLE_LABELS.get(GlobalRole(user.global_role), user.global_role)


async def _people(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not ids:
        return {}
    return {u.id: u for u in await session.scalars(select(User).where(User.id.in_(ids)))}


async def _published_reports(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> list[StatusReport]:
    """Newest first: by report date, then publishing time."""
    if not project_ids:
        return []
    rows = await session.scalars(
        select(StatusReport)
        .where(StatusReport.project_id.in_(project_ids), _published())
        .order_by(
            StatusReport.report_date.desc(), StatusReport.published_at.desc(), StatusReport.id
        )
    )
    return list(rows)


async def _visible_milestones(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> list[MilestoneOut]:
    """Milestones marked visible to the client, by due date."""
    shown = [m for m in await roadmap.active_milestones(session, project_ids) if m.client_visible]
    return await roadmap.milestones_out(session, shown, for_client=True)


def _client_milestone(m: MilestoneOut) -> ClientMilestoneOut:
    return ClientMilestoneOut(
        id=m.id,
        code=m.code,
        name=m.name,
        due_date=m.due_date,
        state=m.state,
        progress=m.progress,
        completed_on=m.completed_at.date() if m.completed_at else None,
        original_due_date=m.original_due_date,
        requested_date=m.requested_date,
        change_request_code=m.change_request_code,
    )


async def _leads(session: AsyncSession, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
    """The first active project lead (by name) of each project."""
    if not project_ids:
        return {}
    rows = await session.execute(
        select(ProjectMember.project_id, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.project_id.in_(project_ids),
            ProjectMember.project_role == ProjectRole.PROJECT_LEAD.value,
            User.is_active.is_(True),
        )
        .order_by(User.name, User.id)
    )
    found: dict[uuid.UUID, User] = {}
    for project_id, user in rows.all():
        found.setdefault(project_id, user)
    return found


def _report_event(report: StatusReport, names: dict[uuid.UUID, str]) -> ClientUpdateOut:
    assert report.published_at is not None
    return ClientUpdateOut(
        kind="report",
        project_id=report.project_id,
        project_name=names[report.project_id],
        title=_title(report),
        occurred_at=report.published_at,
        report_id=report.id,
        change_request_id=None,
        status=None,
    )


async def _events(
    session: AsyncSession, reports: list[StatusReport], names: dict[uuid.UUID, str]
) -> list[ClientUpdateOut]:
    """Published reports, change requests raised, taken into review and decided, and shared
    milestones (shared with the client, reached); newest first, at most MAX_UPDATES."""
    events = [_report_event(r, names) for r in reports if r.published_at is not None]
    if names:
        milestones = await session.scalars(
            select(Milestone).where(
                Milestone.project_id.in_(list(names)),
                Milestone.client_visible.is_(True),
                Milestone.archived_at.is_(None),
            )
        )
        for m in milestones:
            for at, state in ((m.shared_at, "shared"), (m.completed_at, "done")):
                if at is not None:
                    events.append(
                        ClientUpdateOut(
                            kind="milestone",
                            project_id=m.project_id,
                            project_name=names[m.project_id],
                            title=f"{m.code} {m.name}",
                            occurred_at=at,
                            report_id=None,
                            change_request_id=None,
                            milestone_id=m.id,
                            due_date=m.due_date,
                            status=state,
                        )
                    )
        requests = await session.scalars(
            select(ChangeRequest).where(ChangeRequest.project_id.in_(list(names)))
        )
        for cr in requests:
            steps = [(cr.created_at, ChangeRequestStatus.PENDING)]
            if cr.review_started_at:
                steps.append((cr.review_started_at, ChangeRequestStatus.IN_REVIEW))
            if cr.decided_at:
                steps.append((cr.decided_at, ChangeRequestStatus(cr.status)))
            events += [
                ClientUpdateOut(
                    kind="change_request",
                    project_id=cr.project_id,
                    project_name=names[cr.project_id],
                    title=f"{cr.code} {cr.title}",
                    occurred_at=at,
                    report_id=None,
                    change_request_id=cr.id,
                    status=status,
                )
                for at, status in steps
            ]
    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events[:MAX_UPDATES]


def _brief(report: StatusReport) -> ClientReportBrief:
    assert report.published_at is not None  # published reports always have it
    return ClientReportBrief(
        id=report.id,
        title=_title(report),
        report_date=report.report_date,
        health=HEALTH_OF_RAG[report.rag],
        progress=report.progress_percent,
        summary=report.summary,
        published_at=report.published_at,
    )


async def _projects_out(
    session: AsyncSession,
    projects: list[Project],
    reports: list[StatusReport],
    milestones: list[MilestoneOut],
) -> list[ClientProjectOut]:
    upcoming: dict[uuid.UUID, MilestoneOut] = {}
    for m in milestones:  # by due date, so the first open one per project wins
        if not m.done:
            upcoming.setdefault(m.project_id, m)
    newest: dict[uuid.UUID, StatusReport] = {}
    with_progress: dict[uuid.UUID, StatusReport] = {}
    for report in reports:  # newest first, so the first one per project wins
        newest.setdefault(report.project_id, report)
        if report.progress_percent is not None:
            with_progress.setdefault(report.project_id, report)
    publishers = await _people(session, {r.published_by for r in newest.values() if r.published_by})
    leads = await _leads(session, [p.id for p in projects])
    awaiting = await requirements.awaiting_answer_by_project(session, [p.id for p in projects])
    out = []
    for p in projects:
        latest = newest.get(p.id)
        publisher = publishers.get(latest.published_by) if latest and latest.published_by else None
        shared = with_progress.get(p.id)
        next_one = upcoming.get(p.id)
        lead = leads.get(p.id)
        out.append(
            ClientProjectOut(
                id=p.id,
                code=p.code,
                name=p.name,
                category=p.category,
                status=p.status,
                start_date=p.start_date,
                due_date=p.target_end_date,
                health=HEALTH_OF_RAG[latest.rag] if latest else None,
                progress=shared.progress_percent if shared else None,
                progress_published_on=shared.report_date if shared else None,
                published_on=latest.report_date if latest else None,
                published_by=(
                    PublishedBy(name=publisher.name, role=_role_label(publisher))
                    if publisher
                    else None
                ),
                latest_update=(
                    LatestUpdate(text=latest.summary, date=latest.report_date, report_id=latest.id)
                    if latest
                    else None
                ),
                awaiting_input=awaiting.get(p.id, 0),
                project_manager=ClientPersonOut(name=lead.name, email=lead.email) if lead else None,
                next_milestone=(
                    NextMilestone(
                        id=next_one.id,
                        code=next_one.code,
                        name=next_one.name,
                        due_date=next_one.due_date,
                        state=next_one.state,
                    )
                    if next_one
                    else None
                ),
            )
        )
    return out


async def portal(session: AsyncSession, user: User) -> ClientPortalOut:
    """Dashboard and project list in one answer."""
    organisation = (
        await session.get(Organisation, user.organisation_id) if user.organisation_id else None
    )
    projects = list(
        await session.scalars(select(Project).where(_visible(user)).order_by(Project.code))
    )
    reports = await _published_reports(session, [p.id for p in projects])
    milestones = await _visible_milestones(session, [p.id for p in projects])
    items = await _projects_out(session, projects, reports, milestones)
    names = {p.id: p.name for p in projects}
    health: Counter[str] = Counter(item.health or "none" for item in items)
    today = roadmap.today()
    soon = [
        m
        for m in milestones
        if not m.done and today <= m.due_date <= today + timedelta(days=UPCOMING_DAYS)
    ]
    newest = max(reports, key=lambda r: r.published_at or r.created_at, default=None)
    return ClientPortalOut(
        organisation=(
            ClientOrganisationOut(id=organisation.id, name=organisation.name)
            if organisation
            else None
        ),
        projects=items,
        kpis=ClientKpis(
            active_projects=sum(1 for p in projects if p.status not in CLOSED_PROJECT_STATUSES),
            awaiting_input=await requirements.awaiting_answer_count(
                session, [p.id for p in projects]
            ),
            upcoming_milestones=len(soon),
            shared_reports=len(reports),
        ),
        latest_report=(
            ClientLatestReport(
                **_brief(newest).model_dump(),
                project_id=newest.project_id,
                project_name=names[newest.project_id],
            )
            if newest
            else None
        ),
        upcoming_milestones=[
            ClientUpcomingMilestone(
                **_client_milestone(m).model_dump(),
                project_id=m.project_id,
                project_name=names[m.project_id],
            )
            for m in soon
        ],
        updates=await _events(session, reports, names),
        summary={
            "total": len(items),
            **{key: health.get(key, 0) for key in ("on_track", "at_risk", "off_track", "none")},
        },
    )


async def get_project(session: AsyncSession, user: User, project_id: uuid.UUID) -> Project:
    project = await session.scalar(select(Project).where(Project.id == project_id, _visible(user)))
    if project is None:
        raise _not_found()
    return project


async def contacts(session: AsyncSession, project: Project) -> list[ClientContactOut]:
    """Project leads, the client's account managers, then the project's stakeholders (name,
    role and contact details only; the internal influence rating and notes stay out)."""
    found: list[ClientContactOut] = []
    leads = await session.scalars(
        select(User)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(
            ProjectMember.project_id == project.id,
            ProjectMember.project_role == ProjectRole.PROJECT_LEAD.value,
            User.is_active.is_(True),
        )
        .order_by(User.name, User.id)
    )
    for lead in leads:
        found.append(
            ClientContactOut(
                name=lead.name, role="Project Manager", email=lead.email, phone=lead.phone
            )
        )
    if project.client_organisation_id:
        managers = await session.scalars(
            select(User)
            .join(OrganisationAccountManager, OrganisationAccountManager.user_id == User.id)
            .where(
                OrganisationAccountManager.organisation_id == project.client_organisation_id,
                User.is_active.is_(True),
            )
            .order_by(User.name, User.id)
        )
        for manager in managers:
            found.append(
                ClientContactOut(
                    name=manager.name,
                    role="Account Manager",
                    email=manager.email,
                    phone=manager.phone,
                )
            )
    stakeholders = await session.scalars(
        select(Stakeholder)
        .where(Stakeholder.project_id == project.id, Stakeholder.archived_at.is_(None))
        .order_by(Stakeholder.name, Stakeholder.id)
    )
    for person in stakeholders:
        found.append(
            ClientContactOut(
                name=person.name,
                role=person.role_title or "Stakeholder",
                email=person.email,
                phone=person.phone,
            )
        )
    return found


async def project_detail(
    session: AsyncSession, user: User, project_id: uuid.UUID
) -> ClientProjectDetailOut:
    project = await get_project(session, user, project_id)
    reports = await _published_reports(session, [project.id])
    milestones = await _visible_milestones(session, [project.id])
    base = (await _projects_out(session, [project], reports, milestones))[0]
    return ClientProjectDetailOut(
        **base.model_dump(),
        description=project.description,
        contacts=await contacts(session, project),
        reports=[_brief(r) for r in reports],
        milestones=[_client_milestone(m) for m in milestones],
        activity=await _events(session, reports, {project.id: project.name}),
        change_requests=[
            ClientChangeRequestBrief(
                id=r.id, code=r.code, title=r.title, status=ChangeRequestStatus(r.status)
            )
            for r in (await change_requests.list_requests(session, project.id))[0]
        ],
    )


async def project_roadmap(
    session: AsyncSession, user: User, project_id: uuid.UUID
) -> ClientRoadmapOut:
    """Only phases and milestones marked visible to the client. A visible milestone in a hidden
    phase is shown outside any phase. A phase's status and completed share count all of its
    milestones (a summary; hidden milestones themselves never appear)."""
    project = await get_project(session, user, project_id)
    full = await roadmap.build_roadmap(session, project.id, for_client=True)
    phases = [(phase, out) for phase, out, _ in full.phases if phase.client_visible]
    shown_phase_ids = {phase.id for phase, _ in phases}
    visible = [m for m in full.milestones if m.client_visible]
    dates = [m.due_date for m in visible]
    for phase, _ in phases:
        dates += [phase.start_date, phase.end_date]
    start, end = roadmap.date_range(project, dates)
    return ClientRoadmapOut(
        project_id=project.id,
        today=roadmap.today(),
        range_start=start,
        range_end=end,
        phases=[
            ClientPhaseOut(
                id=out.id,
                name=out.name,
                start_date=out.start_date,
                end_date=out.end_date,
                status=out.status,
                progress=out.progress,
                milestones=[_client_milestone(m) for m in visible if m.phase_id == phase.id],
            )
            for phase, out in phases
        ],
        unphased_milestones=[
            _client_milestone(m) for m in visible if m.phase_id not in shown_phase_ids
        ],
    )


async def get_report(
    session: AsyncSession, user: User, project_id: uuid.UUID, report_id: uuid.UUID
) -> ClientReportOut:
    """A published report of a visible project; drafts and other projects' reports are 404."""
    project = await get_project(session, user, project_id)
    report = await session.scalar(
        select(StatusReport).where(
            StatusReport.id == report_id, StatusReport.project_id == project.id, _published()
        )
    )
    if report is None:
        raise AppError(404, "NOT_FOUND", "Report not found.")
    return await report_document(session, report, project)


async def report_document(
    session: AsyncSession, report: StatusReport, project: Project
) -> ClientReportOut:
    """The shared, published content of a report: what the client sees and what every PDF
    download contains (client portal and staff)."""
    publisher = await session.get(User, report.published_by) if report.published_by else None
    return ClientReportOut(
        **_brief(report).model_dump(),
        achievements=report.achievements,
        next_steps=report.next_steps,
        risks=report.risks,
        published_by=(
            PublishedBy(name=publisher.name, role=_role_label(publisher)) if publisher else None
        ),
        project_id=project.id,
        project_name=project.name,
    )


# --- change requests ----------------------------------------------------------------------------


async def _requests_out(
    session: AsyncSession, requests: list[ChangeRequest]
) -> list[ClientChangeRequestOut]:
    full = await change_requests.requests_out(session, requests)
    milestone_ids = {r.milestone_id for r in requests if r.milestone_id}
    shown = (
        {
            m.id
            for m in await session.scalars(
                select(Milestone).where(
                    Milestone.id.in_(milestone_ids), Milestone.client_visible.is_(True)
                )
            )
        }
        if milestone_ids
        else set()
    )
    return [
        ClientChangeRequestOut(
            id=r.id,
            code=r.code,
            title=r.title,
            status=r.status,
            description=r.description,
            reason=r.reason,
            milestone=(
                ClientMilestoneRef(code=r.milestone.code, name=r.milestone.name)
                if r.milestone and r.milestone.id in shown
                else None
            ),
            requested_date=r.requested_date if r.milestone and r.milestone.id in shown else None,
            review_started_at=r.review_started_at,
            impact_schedule_days=r.impact_schedule_days,
            impact_scope=r.impact_scope,
            decision_note=r.decision_note,
            decided_at=r.decided_at,
            submitted_by=r.submitted_by.name,
            submitted_at=r.created_at,
        )
        for r in full
    ]


async def list_change_requests(
    session: AsyncSession, user: User, project_id: uuid.UUID
) -> ClientChangeRequestListOut:
    project = await get_project(session, user, project_id)
    requests, counts = await change_requests.list_requests(session, project.id)
    return ClientChangeRequestListOut(items=await _requests_out(session, requests), counts=counts)


async def get_change_request(
    session: AsyncSession, user: User, project_id: uuid.UUID, request_id: uuid.UUID
) -> ClientChangeRequestOut:
    project = await get_project(session, user, project_id)
    request = await change_requests.get_request(session, project.id, request_id)
    return (await _requests_out(session, [request]))[0]


async def submit_change_request(
    session: AsyncSession, user: User, project_id: uuid.UUID, data: ChangeRequestCreate
) -> ClientChangeRequestOut:
    """Raised in review; the milestone (if any) must be one shown to the client."""
    project = await get_project(session, user, project_id)
    ensure_writable(project)
    request = await change_requests.create_request(session, user, project.id, data)
    return (await _requests_out(session, [request]))[0]


# --- change request conversation ----------------------------------------------------------------


def _client_comment(c: CommentOut) -> ClientCommentOut:
    return ClientCommentOut(
        id=c.id,
        body=c.body,
        author=c.author.name,
        from_client=c.author_is_client,
        created_at=c.created_at,
    )


def _client_attachment(a: AttachmentOut) -> ClientAttachmentOut:
    return ClientAttachmentOut(
        id=a.id,
        name=a.name,
        content_type=a.content_type,
        size_bytes=a.size_bytes,
        uploaded_by=a.uploaded_by.name,
        created_at=a.created_at,
    )


async def _request_of(
    session: AsyncSession, user: User, project_id: uuid.UUID, request_id: uuid.UUID
) -> tuple[Project, ChangeRequest]:
    project = await get_project(session, user, project_id)
    return project, await change_requests.get_request(session, project.id, request_id)


async def list_comments(
    session: AsyncSession, user: User, project_id: uuid.UUID, request_id: uuid.UUID
) -> list[ClientCommentOut]:
    _, request = await _request_of(session, user, project_id, request_id)
    found = await change_requests.comments_out(session, request.id, include_internal=False)
    return [_client_comment(c) for c in found]


async def add_comment(
    session: AsyncSession, user: User, project_id: uuid.UUID, request_id: uuid.UUID, body: str
) -> ClientCommentOut:
    project, request = await _request_of(session, user, project_id, request_id)
    ensure_writable(project)
    comment = await change_requests.add_comment(session, user, request, body, internal=False)
    return _client_comment(comment)


async def list_attachments(
    session: AsyncSession, user: User, project_id: uuid.UUID, request_id: uuid.UUID
) -> list[ClientAttachmentOut]:
    _, request = await _request_of(session, user, project_id, request_id)
    return [
        _client_attachment(a) for a in await change_requests.attachments_out(session, request.id)
    ]


async def add_attachment(
    session: AsyncSession,
    user: User,
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    upload: UploadFile,
) -> ClientAttachmentOut:
    project, request = await _request_of(session, user, project_id, request_id)
    ensure_writable(project)
    return _client_attachment(await change_requests.add_attachment(session, user, request, upload))


async def download_attachment(
    session: AsyncSession,
    user: User,
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> FileResponse:
    """Access is checked again on every download: own organisation's project only."""
    _, request = await _request_of(session, user, project_id, request_id)
    item = await change_requests.get_attachment(session, request.id, attachment_id)
    return change_requests.file_response(item)


# --- requirements and acceptance ----------------------------------------------------------------


async def list_requirements(
    session: AsyncSession, user: User, project_id: uuid.UUID
) -> ClientRequirementListOut:
    project = await get_project(session, user, project_id)
    rows = await requirements.client_requirements(session, project.id)
    return ClientRequirementListOut(
        items=await requirements.client_out(session, rows), counts=requirements.client_counts(rows)
    )


async def get_requirement(
    session: AsyncSession, user: User, project_id: uuid.UUID, requirement_id: uuid.UUID
) -> ClientRequirementOut:
    project = await get_project(session, user, project_id)
    found = await requirements.client_requirement(session, project.id, requirement_id)
    return (await requirements.client_out(session, [found]))[0]


async def respond_to_requirement(
    session: AsyncSession,
    user: User,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    data: ClientRequirementResponse,
) -> ClientRequirementOut:
    """Accept, request changes or reject the newest published version."""
    project = await get_project(session, user, project_id)
    ensure_writable(project)
    found = await requirements.respond(session, user, project.id, requirement_id, data)
    return (await requirements.client_out(session, [found]))[0]
