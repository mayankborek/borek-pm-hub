"""Status reports (RAG, draft and published) and the stakeholder register of a project."""

import uuid

from fastapi import APIRouter, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action
from app.common.enums import ReportState
from app.common.validation import PageParam, PageSizeParam
from app.core.database import SessionDep
from app.projects.service import allowed_in, authorize, get_project
from app.reporting import service
from app.reporting.models import StatusReport
from app.reporting.schemas import (
    StakeholderCreate,
    StakeholderOut,
    StakeholderUpdate,
    StatusReportCreate,
    StatusReportListOut,
    StatusReportOut,
    StatusReportUpdate,
)
from app.users.models import User

router = APIRouter(prefix="/projects/{project_id}", tags=["reporting"])


async def _one(session: AsyncSession, report: StatusReport) -> StatusReportOut:
    return (await service.reports_out(session, [report]))[0]


async def _sees_drafts(session: AsyncSession, user: User, project_id: uuid.UUID) -> bool:
    project = await get_project(session, project_id)
    return await allowed_in(session, user, project, Action.STATUS_REPORT_MANAGE)


# --- status reports -----------------------------------------------------------------------------


@router.get("/status-reports", response_model=StatusReportListOut)
async def list_status_reports(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    state: ReportState | None = None,
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> StatusReportListOut:
    """Newest first. Everyone who sees the project reads published reports; those who write
    reports also see drafts."""
    await authorize(session, user, project_id, Action.PROJECT_VIEW)
    reports, total = await service.list_reports(
        session,
        project_id,
        include_drafts=await _sees_drafts(session, user, project_id),
        state=state,
        page=page,
        page_size=page_size,
    )
    return StatusReportListOut(
        items=await service.reports_out(session, reports),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/status-reports", response_model=StatusReportOut, status_code=201)
async def create_status_report(
    project_id: uuid.UUID,
    body: StatusReportCreate,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
) -> StatusReportOut:
    """Creates a draft."""
    await authorize(session, user, project_id, Action.STATUS_REPORT_MANAGE, writable=True)
    report = await service.create_report(session, user, project_id, body)
    response.headers["Location"] = f"/api/v1/projects/{project_id}/status-reports/{report.id}"
    return await _one(session, report)


@router.get("/status-reports/{report_id}", response_model=StatusReportOut)
async def get_status_report(
    project_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> StatusReportOut:
    await authorize(session, user, project_id, Action.PROJECT_VIEW)
    report = await service.get_report(
        session,
        project_id,
        report_id,
        include_drafts=await _sees_drafts(session, user, project_id),
    )
    return await _one(session, report)


@router.patch("/status-reports/{report_id}", response_model=StatusReportOut)
async def update_status_report(
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    body: StatusReportUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> StatusReportOut:
    """Drafts only: a published report is history."""
    await authorize(session, user, project_id, Action.STATUS_REPORT_MANAGE, writable=True)
    report = await service.update_report(session, user, project_id, report_id, body)
    return await _one(session, report)


@router.post("/status-reports/{report_id}/publish", response_model=StatusReportOut)
async def publish_status_report(
    project_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> StatusReportOut:
    """Makes the report visible to everyone in the project and its RAG the project's current one."""
    await authorize(session, user, project_id, Action.STATUS_REPORT_MANAGE, writable=True)
    report = await service.publish_report(session, user, project_id, report_id)
    return await _one(session, report)


@router.delete("/status-reports/{report_id}", status_code=204)
async def archive_status_report(
    project_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Drafts only. The row stays in the database."""
    await authorize(session, user, project_id, Action.STATUS_REPORT_MANAGE, writable=True)
    await service.archive_report(session, user, project_id, report_id)


# --- stakeholders -------------------------------------------------------------------------------


@router.get("/stakeholders", response_model=list[StakeholderOut])
async def list_stakeholders(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[StakeholderOut]:
    """Contact details, so only people who manage the register can read it."""
    await authorize(session, user, project_id, Action.STAKEHOLDER_MANAGE)
    return [
        StakeholderOut.model_validate(s, from_attributes=True)
        for s in await service.list_stakeholders(session, project_id)
    ]


@router.post("/stakeholders", response_model=StakeholderOut, status_code=201)
async def create_stakeholder(
    project_id: uuid.UUID, body: StakeholderCreate, user: CurrentUser, session: SessionDep
) -> StakeholderOut:
    await authorize(session, user, project_id, Action.STAKEHOLDER_MANAGE, writable=True)
    stakeholder = await service.create_stakeholder(session, user, project_id, body)
    return StakeholderOut.model_validate(stakeholder, from_attributes=True)


@router.patch("/stakeholders/{stakeholder_id}", response_model=StakeholderOut)
async def update_stakeholder(
    project_id: uuid.UUID,
    stakeholder_id: uuid.UUID,
    body: StakeholderUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> StakeholderOut:
    await authorize(session, user, project_id, Action.STAKEHOLDER_MANAGE, writable=True)
    stakeholder = await service.update_stakeholder(session, user, project_id, stakeholder_id, body)
    return StakeholderOut.model_validate(stakeholder, from_attributes=True)


@router.delete("/stakeholders/{stakeholder_id}", status_code=204)
async def archive_stakeholder(
    project_id: uuid.UUID, stakeholder_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await authorize(session, user, project_id, Action.STAKEHOLDER_MANAGE, writable=True)
    await service.archive_stakeholder(session, user, project_id, stakeholder_id)
