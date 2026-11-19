"""Client portal data. One rule decides what a client sees (`_visible`): the external, not archived
projects of the client's own organisation. Everything is read-only, and only published status
reports leave this module; tasks, effort, activity, drafts and money never do."""

import uuid
from collections import Counter

from sqlalchemy import ColumnElement, and_, false, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.client.schemas import (
    HEALTH_OF_RAG,
    ClientContactOut,
    ClientOrganisationOut,
    ClientPortalOut,
    ClientProjectDetailOut,
    ClientProjectOut,
    ClientReportBrief,
    ClientReportOut,
    ClientUpdateOut,
    LatestUpdate,
    PublishedBy,
)
from app.common.enums import (
    GLOBAL_ROLE_LABELS,
    GlobalRole,
    ProjectRole,
    ProjectType,
    ReportState,
)
from app.core.errors import AppError
from app.organisations.models import Organisation, OrganisationAccountManager
from app.projects.models import Project, ProjectMember
from app.projects.service import task_summaries
from app.reporting.models import Stakeholder, StatusReport
from app.users.models import User

MAX_UPDATES = 10


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


def _brief(report: StatusReport) -> ClientReportBrief:
    assert report.published_at is not None  # published reports always have it
    return ClientReportBrief(
        id=report.id,
        title=_title(report),
        report_date=report.report_date,
        health=HEALTH_OF_RAG[report.rag],
        summary=report.summary,
        published_at=report.published_at,
    )


async def _projects_out(
    session: AsyncSession, projects: list[Project], reports: list[StatusReport]
) -> list[ClientProjectOut]:
    summaries = await task_summaries(session, [p.id for p in projects])
    newest: dict[uuid.UUID, StatusReport] = {}
    for report in reports:  # newest first, so the first one per project wins
        newest.setdefault(report.project_id, report)
    publishers = await _people(session, {r.published_by for r in newest.values() if r.published_by})
    out = []
    for p in projects:
        latest = newest.get(p.id)
        publisher = publishers.get(latest.published_by) if latest and latest.published_by else None
        summary = summaries.get(p.id)
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
                progress=summary.completion_percent if summary else 0,
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
    items = await _projects_out(session, projects, reports)
    names = {p.id: p.name for p in projects}
    health: Counter[str] = Counter(item.health or "none" for item in items)
    return ClientPortalOut(
        organisation=(
            ClientOrganisationOut(id=organisation.id, name=organisation.name)
            if organisation
            else None
        ),
        projects=items,
        updates=[
            ClientUpdateOut(
                report_id=r.id,
                project_id=r.project_id,
                project_name=names[r.project_id],
                title=_title(r),
                published_at=r.published_at,
            )
            for r in sorted(reports, key=lambda r: r.published_at or r.created_at, reverse=True)[
                :MAX_UPDATES
            ]
            if r.published_at is not None
        ],
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
    base = (await _projects_out(session, [project], reports))[0]
    return ClientProjectDetailOut(
        **base.model_dump(),
        description=project.description,
        contacts=await contacts(session, project),
        reports=[_brief(r) for r in reports],
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
