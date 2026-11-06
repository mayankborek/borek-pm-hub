"""Status reports and stakeholders. Routers check permissions; rules live here."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.common.enums import ReportState
from app.core.errors import AppError
from app.organisations.schemas import PersonBrief
from app.reporting.models import Stakeholder, StatusReport
from app.reporting.schemas import (
    StakeholderCreate,
    StakeholderUpdate,
    StatusReportCreate,
    StatusReportOut,
    StatusReportUpdate,
)
from app.users.models import User


def _version_conflict(what: str) -> AppError:
    return AppError(409, "VERSION_CONFLICT", f"The {what} was changed by someone else. Reload.")


# --- status reports -----------------------------------------------------------------------------


def _report_not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Status report not found.")


async def _people(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, PersonBrief]:
    if not ids:
        return {}
    rows = await session.scalars(select(User).where(User.id.in_(ids)))
    return {u.id: PersonBrief(id=u.id, name=u.name, email=u.email) for u in rows}


async def reports_out(session: AsyncSession, reports: list[StatusReport]) -> list[StatusReportOut]:
    ids = {r.created_by for r in reports} | {r.published_by for r in reports if r.published_by}
    people = await _people(session, ids)
    return [
        StatusReportOut(
            id=r.id,
            project_id=r.project_id,
            rag=r.rag,
            summary=r.summary,
            achievements=r.achievements,
            next_steps=r.next_steps,
            risks=r.risks,
            report_date=r.report_date,
            state=r.state,
            published_at=r.published_at,
            published_by=people.get(r.published_by) if r.published_by else None,
            author=people[r.created_by],
            version=r.version,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in reports
    ]


async def list_reports(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    include_drafts: bool,
    state: ReportState | None,
    page: int,
    page_size: int,
) -> tuple[list[StatusReport], int]:
    """Newest first. People who cannot manage reports only ever get published ones."""
    conditions: list[ColumnElement[bool]] = [
        StatusReport.project_id == project_id,
        StatusReport.archived_at.is_(None),
    ]
    if not include_drafts:
        conditions.append(StatusReport.state == ReportState.PUBLISHED.value)
    if state:
        conditions.append(StatusReport.state == state.value)
    total = await session.scalar(select(func.count(StatusReport.id)).where(*conditions)) or 0
    rows = await session.scalars(
        select(StatusReport)
        .where(*conditions)
        .order_by(StatusReport.report_date.desc(), StatusReport.created_at.desc(), StatusReport.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


async def get_report(
    session: AsyncSession, project_id: uuid.UUID, report_id: uuid.UUID, *, include_drafts: bool
) -> StatusReport:
    report = await session.get(StatusReport, report_id)
    if report is None or report.project_id != project_id or report.archived_at is not None:
        raise _report_not_found()
    if report.state != ReportState.PUBLISHED.value and not include_drafts:
        raise _report_not_found()
    return report


def _ensure_draft(report: StatusReport) -> None:
    if report.state != ReportState.DRAFT.value:
        raise AppError(
            409, "REPORT_PUBLISHED", "A published report cannot change. Write a new one instead."
        )


async def create_report(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: StatusReportCreate
) -> StatusReport:
    report = StatusReport(
        project_id=project_id,
        rag=data.rag.value,
        summary=data.summary,
        achievements=data.achievements,
        next_steps=data.next_steps,
        risks=data.risks,
        report_date=data.report_date or datetime.now(UTC).date(),
        created_by=actor.id,
    )
    session.add(report)
    await session.flush()
    record_audit(
        session,
        actor,
        "status_report.created",
        "status_report",
        report.id,
        project_id=project_id,
        after={"rag": report.rag},
    )
    await session.commit()
    await session.refresh(report)
    return report


async def update_report(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    data: StatusReportUpdate,
) -> StatusReport:
    report = await get_report(session, project_id, report_id, include_drafts=True)
    _ensure_draft(report)
    if data.version != report.version:
        raise _version_conflict("report")
    for field, value in data.model_dump(exclude={"version"}, exclude_unset=True).items():
        setattr(report, field, value.value if field == "rag" else value)
    record_audit(
        session,
        actor,
        "status_report.updated",
        "status_report",
        report.id,
        project_id=project_id,
        after={"rag": report.rag},
    )
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise _version_conflict("report") from None
    await session.refresh(report)
    return report


async def publish_report(
    session: AsyncSession, actor: User, project_id: uuid.UUID, report_id: uuid.UUID
) -> StatusReport:
    """Publishing makes it the project's current RAG. Publishing twice is refused."""
    report = await get_report(session, project_id, report_id, include_drafts=True)
    _ensure_draft(report)
    report.state = ReportState.PUBLISHED.value
    report.published_at = datetime.now(UTC)
    report.published_by = actor.id
    record_audit(
        session,
        actor,
        "status_report.published",
        "status_report",
        report.id,
        project_id=project_id,
        after={"rag": report.rag},
    )
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise _version_conflict("report") from None
    await session.refresh(report)
    return report


async def archive_report(
    session: AsyncSession, actor: User, project_id: uuid.UUID, report_id: uuid.UUID
) -> None:
    """Only drafts can be removed. They are archived, not deleted."""
    report = await get_report(session, project_id, report_id, include_drafts=True)
    _ensure_draft(report)
    report.archived_at = datetime.now(UTC)
    record_audit(
        session,
        actor,
        "status_report.archived",
        "status_report",
        report.id,
        project_id=project_id,
    )
    await session.commit()


def latest_published() -> Select[tuple[uuid.UUID, str, date]]:
    """One row per project with a published report: project id, RAG and date of the newest."""
    return (
        select(StatusReport.project_id, StatusReport.rag, StatusReport.report_date)
        .where(
            StatusReport.state == ReportState.PUBLISHED.value,
            StatusReport.archived_at.is_(None),
        )
        .distinct(StatusReport.project_id)
        .order_by(
            StatusReport.project_id,
            StatusReport.report_date.desc(),
            StatusReport.published_at.desc(),
        )
    )


# --- stakeholders -------------------------------------------------------------------------------


def _stakeholder_not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Stakeholder not found.")


async def _get_stakeholder(
    session: AsyncSession, project_id: uuid.UUID, stakeholder_id: uuid.UUID
) -> Stakeholder:
    stakeholder = await session.get(Stakeholder, stakeholder_id)
    if (
        stakeholder is None
        or stakeholder.project_id != project_id
        or stakeholder.archived_at is not None
    ):
        raise _stakeholder_not_found()
    return stakeholder


async def list_stakeholders(session: AsyncSession, project_id: uuid.UUID) -> list[Stakeholder]:
    rows = await session.scalars(
        select(Stakeholder)
        .where(Stakeholder.project_id == project_id, Stakeholder.archived_at.is_(None))
        .order_by(Stakeholder.name, Stakeholder.id)
    )
    return list(rows)


async def create_stakeholder(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: StakeholderCreate
) -> Stakeholder:
    values = data.model_dump()
    influence = values.pop("influence")
    stakeholder = Stakeholder(
        project_id=project_id,
        created_by=actor.id,
        influence=influence.value if influence else None,
        **values,
    )
    session.add(stakeholder)
    await session.flush()
    record_audit(
        session,
        actor,
        "stakeholder.added",
        "stakeholder",
        stakeholder.id,
        project_id=project_id,
        after={"name": stakeholder.name},
    )
    await session.commit()
    await session.refresh(stakeholder)
    return stakeholder


async def update_stakeholder(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    stakeholder_id: uuid.UUID,
    data: StakeholderUpdate,
) -> Stakeholder:
    stakeholder = await _get_stakeholder(session, project_id, stakeholder_id)
    if data.version != stakeholder.version:
        raise _version_conflict("stakeholder")
    changes = data.model_dump(exclude={"version"}, exclude_unset=True)
    for field, value in changes.items():
        setattr(stakeholder, field, value.value if field == "influence" and value else value)
    record_audit(  # the fields changed, not their values: contact details stay out of the log
        session,
        actor,
        "stakeholder.updated",
        "stakeholder",
        stakeholder.id,
        project_id=project_id,
        after={"changed": sorted(changes)},
    )
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise _version_conflict("stakeholder") from None
    await session.refresh(stakeholder)
    return stakeholder


async def archive_stakeholder(
    session: AsyncSession, actor: User, project_id: uuid.UUID, stakeholder_id: uuid.UUID
) -> None:
    stakeholder = await _get_stakeholder(session, project_id, stakeholder_id)
    stakeholder.archived_at = datetime.now(UTC)
    record_audit(
        session,
        actor,
        "stakeholder.archived",
        "stakeholder",
        stakeholder.id,
        project_id=project_id,
        before={"name": stakeholder.name},
    )
    await session.commit()
