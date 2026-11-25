"""Generate, edit, share and archive project reports; who may read which.

Staff: people who write status reports (project leads, Managers, the client's Account Manager)
generate, edit and share. Project leads and Managers read every report of the project; an
Account Manager reads the ones shared with the Account Manager and their own. Clients read the
ones shared with the client portal (app/client). Developers do not see generated reports.
A shared report cannot be edited (what people were given stays as it is): unshare it first.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.auth.permissions import is_account_manager, sees_all_projects
from app.core.errors import AppError
from app.notifications.service import account_managers, client_contacts, managers, notify
from app.organisations.models import Organisation
from app.organisations.schemas import PersonBrief
from app.project_reports import content as builder
from app.project_reports.models import Audience, PeriodKind, ProjectReport, ReportKind
from app.project_reports.schemas import (
    ClientReportBrief,
    ClientReportDetail,
    ReportBrief,
    ReportContent,
    ReportOut,
    ReportSettings,
)
from app.projects.membership import lead_rights_in
from app.projects.models import Project
from app.users.models import User


def not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Report not found.")


def _conflict() -> AppError:
    return AppError(
        409, "VERSION_CONFLICT", "The report was changed by someone else. Reload and try again."
    )


async def _sees_all(session: AsyncSession, user: User, project_id: uuid.UUID) -> bool:
    return sees_all_projects(user) or await lead_rights_in(session, user, project_id)


def _readable_by(user: User) -> Any:
    """Extra condition for an Account Manager (callers handle leads and Managers)."""
    return (ProjectReport.prepared_by == user.id) | ProjectReport.shared_with.contains(
        [Audience.ACCOUNT_MANAGER.value]
    )


async def list_reports(
    session: AsyncSession,
    user: User,
    project_id: uuid.UUID,
    *,
    kind: ReportKind | None,
    shared_with: Audience | None,
    page: int,
    page_size: int,
) -> tuple[list[ProjectReport], int]:
    conditions: list[Any] = [
        ProjectReport.project_id == project_id,
        ProjectReport.archived_at.is_(None),
    ]
    if not await _sees_all(session, user, project_id):
        conditions.append(_readable_by(user))
    if kind:
        conditions.append(ProjectReport.kind == kind.value)
    if shared_with:
        conditions.append(ProjectReport.shared_with.contains([shared_with.value]))
    total = await session.scalar(select(func.count(ProjectReport.id)).where(*conditions)) or 0
    rows = await session.scalars(
        select(ProjectReport)
        .where(*conditions)
        .order_by(ProjectReport.created_at.desc(), ProjectReport.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


async def get_report(
    session: AsyncSession, user: User, project_id: uuid.UUID, report_id: uuid.UUID
) -> ProjectReport:
    report = await session.scalar(
        select(ProjectReport).where(
            ProjectReport.id == report_id,
            ProjectReport.project_id == project_id,
            ProjectReport.archived_at.is_(None),
        )
    )
    if report is None:
        raise not_found()
    if not await _sees_all(session, user, project_id) and not (
        is_account_manager(user)
        and (report.prepared_by == user.id or Audience.ACCOUNT_MANAGER.value in report.shared_with)
    ):
        raise not_found()
    return report


async def _apply(
    session: AsyncSession, report: ProjectReport, project: Project, data: ReportSettings
) -> None:
    assert data.period_kind is not None
    built = await builder.build(session, project, data.kind, data.period_start, data.period_end)
    report.kind = data.kind.value
    report.title = data.title or builder.default_title(data.kind, data.period_kind)
    report.period_kind = data.period_kind.value
    report.period_start = data.period_start
    report.period_end = data.period_end
    report.summary = data.summary
    report.content = built.model_dump()
    report.generated_at = datetime.now(UTC)


async def generate(
    session: AsyncSession, actor: User, project: Project, data: ReportSettings
) -> ProjectReport:
    report = ProjectReport(project_id=project.id, prepared_by=actor.id)
    await _apply(session, report, project, data)
    session.add(report)
    await session.flush()
    record_audit(
        session,
        actor,
        "project_report.generated",
        "project_report",
        report.id,
        project_id=project.id,
        after={"kind": report.kind, "title": report.title},
    )
    await session.commit()
    await session.refresh(report)
    return report


async def edit(
    session: AsyncSession,
    actor: User,
    project: Project,
    report: ProjectReport,
    data: ReportSettings,
    version: int,
) -> ProjectReport:
    """Edit report: new settings, data generated again now (same report, prepared by the
    editor). Not while it is shared."""
    if version != report.version:
        raise _conflict()
    if report.shared_with:
        raise AppError(
            409,
            "REPORT_SHARED",
            "This report is shared. Stop sharing it before you change it, or generate a new one.",
        )
    await _apply(session, report, project, data)
    report.prepared_by = actor.id
    record_audit(
        session,
        actor,
        "project_report.updated",
        "project_report",
        report.id,
        project_id=project.id,
        after={"kind": report.kind, "title": report.title},
    )
    await _commit(session)
    await session.refresh(report)
    return report


async def _commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise _conflict() from None


async def share(
    session: AsyncSession,
    actor: User,
    project: Project,
    report: ProjectReport,
    audiences: list[Audience],
    version: int,
) -> ProjectReport:
    """Set who can view it (the full list). Newly added audiences are notified."""
    if version != report.version:
        raise _conflict()
    wanted = sorted({a.value for a in audiences})
    if Audience.CLIENT.value in wanted and (
        project.project_type != "external" or project.client_organisation_id is None
    ):
        raise AppError(
            409,
            "NO_CLIENT_PORTAL",
            "Only external projects with a client can share reports with the client portal.",
        )
    added = set(wanted) - set(report.shared_with)
    if wanted == sorted(report.shared_with):
        return report
    report.shared_with = wanted
    report.shared_at = datetime.now(UTC)
    report.shared_by = actor.id
    record_audit(
        session,
        actor,
        "project_report.shared",
        "project_report",
        report.id,
        project_id=project.id,
        after={"shared_with": wanted},
    )
    recipients: list[uuid.UUID] = []
    if Audience.ACCOUNT_MANAGER.value in added:
        recipients += await account_managers(session, project)
    if Audience.MANAGER.value in added:
        recipients += await managers(session)
    if Audience.CLIENT.value in added:
        recipients += await client_contacts(session, project)
    if recipients:
        await notify(
            session,
            actor,
            "project_report.shared",
            entity_type="project_report",
            entity_id=report.id,
            project_id=project.id,
            params={"title": report.title, "kind": report.kind},
            recipients=[(i, "reports") for i in dict.fromkeys(recipients)],
        )
    await _commit(session)
    await session.refresh(report)
    return report


async def archive(
    session: AsyncSession, actor: User, report: ProjectReport, version: int | None = None
) -> None:
    """Delete = archive: hidden everywhere (also for the audiences it was shared with)."""
    if report.archived_at is None:
        report.archived_at = datetime.now(UTC)
        record_audit(
            session,
            actor,
            "project_report.archived",
            "project_report",
            report.id,
            project_id=report.project_id,
        )
        await _commit(session)


# --- output -----------------------------------------------------------------------------------


async def _people(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not ids:
        return {}
    return {u.id: u for u in await session.scalars(select(User).where(User.id.in_(ids)))}


def _brief(user: User) -> PersonBrief:
    return PersonBrief(id=user.id, name=user.name, email=user.email)


async def briefs(session: AsyncSession, reports: list[ProjectReport]) -> list[ReportBrief]:
    people = await _people(
        session,
        {r.prepared_by for r in reports} | {r.shared_by for r in reports if r.shared_by},
    )
    return [
        ReportBrief(
            id=r.id,
            project_id=r.project_id,
            kind=ReportKind(r.kind),
            title=r.title,
            period_kind=PeriodKind(r.period_kind),
            period_start=r.period_start,
            period_end=r.period_end,
            prepared_by=_brief(people[r.prepared_by]),
            generated_at=r.generated_at,
            shared_with=[Audience(a) for a in r.shared_with],
            shared_at=r.shared_at,
            shared_by=_brief(people[r.shared_by]) if r.shared_by else None,
            version=r.version,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in reports
    ]


async def client_name(session: AsyncSession, project: Project) -> str | None:
    if project.client_organisation_id is None:
        return None
    organisation = await session.get(Organisation, project.client_organisation_id)
    return organisation.name if organisation else None


async def report_out(session: AsyncSession, report: ProjectReport, project: Project) -> ReportOut:
    brief = (await briefs(session, [report]))[0]
    return ReportOut(
        **brief.model_dump(),
        project_name=project.name,
        project_code=project.code,
        client_name=await client_name(session, project),
        summary=report.summary,
        content=ReportContent.model_validate(report.content),
    )


def period_text(report: ProjectReport) -> str:
    if report.period_start is None or report.period_end is None:
        return "Overall"
    return f"{report.period_start:%d.%m.%Y} - {report.period_end:%d.%m.%Y}"


# --- client portal ----------------------------------------------------------------------------


def _shared_with_client() -> Any:
    return ProjectReport.shared_with.contains([Audience.CLIENT.value]) & (
        ProjectReport.archived_at.is_(None)
    )


async def client_reports(session: AsyncSession, project: Project) -> list[ClientReportBrief]:
    reports = list(
        await session.scalars(
            select(ProjectReport)
            .where(ProjectReport.project_id == project.id, _shared_with_client())
            .order_by(ProjectReport.shared_at.desc(), ProjectReport.id)
        )
    )
    people = await _people(session, {r.prepared_by for r in reports})
    return [
        ClientReportBrief(
            id=r.id,
            kind=ReportKind(r.kind),
            title=r.title,
            period_kind=PeriodKind(r.period_kind),
            period_start=r.period_start,
            period_end=r.period_end,
            prepared_by=people[r.prepared_by].name,
            shared_at=r.shared_at,
        )
        for r in reports
    ]


async def client_report(
    session: AsyncSession, project: Project, report_id: uuid.UUID
) -> tuple[ProjectReport, ClientReportDetail]:
    report = await session.scalar(
        select(ProjectReport).where(
            ProjectReport.id == report_id,
            ProjectReport.project_id == project.id,
            _shared_with_client(),
        )
    )
    if report is None:
        raise not_found()
    preparer = await session.get(User, report.prepared_by)
    assert preparer is not None
    return report, ClientReportDetail(
        id=report.id,
        kind=ReportKind(report.kind),
        title=report.title,
        period_kind=PeriodKind(report.period_kind),
        period_start=report.period_start,
        period_end=report.period_end,
        prepared_by=preparer.name,
        shared_at=report.shared_at,
        project_name=project.name,
        client_name=await client_name(session, project),
        summary=report.summary,
        content=ReportContent.model_validate(report.content),
        generated_at=report.generated_at,
    )
