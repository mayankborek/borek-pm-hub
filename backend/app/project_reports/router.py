"""Generated reports (BB-21 / RD-11): Reports tab > Generate report > Report preview >
Download / Send (share in the app) / Edit report. Clients read shared ones in the portal."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require
from app.client import service as client_service
from app.common.validation import PageParam, PageSizeParam
from app.core.database import SessionDep
from app.project_reports import service
from app.project_reports.models import Audience, ProjectReport, ReportKind
from app.project_reports.pdf import build_pdf
from app.project_reports.schemas import (
    ClientReportDetail,
    ClientReportListOut,
    ReportContent,
    ReportEdit,
    ReportListOut,
    ReportOut,
    ReportSettings,
    ReportShare,
)
from app.projects.models import Project
from app.projects.service import authorize
from app.users.models import User

router = APIRouter(tags=["project reports"])
STAFF = "/projects/{project_id}/reports"
CLIENT = "/client/projects/{project_id}/shared-reports"
PDF: dict[int | str, dict[str, Any]] = {
    200: {"content": {"application/pdf": {"schema": {"type": "string"}}}}
}

AUDIENCE_LABEL = {"account_manager": "Account Manager", "client": "Client", "manager": "Manager"}


async def _project(
    session: AsyncSession, user: User, project_id: uuid.UUID, *, writable: bool = False
) -> Project:
    return await authorize(
        session, user, project_id, Action.STATUS_REPORT_MANAGE, writable=writable
    )


async def _pdf_response(
    session: AsyncSession, report: ProjectReport, project: Project, audience: str
) -> Response:
    preparer = await session.get(User, report.prepared_by)
    data = build_pdf(
        project_name=project.name,
        project_code=project.code,
        title=report.title,
        client_name=await service.client_name(session, project),
        period=service.period_text(report),
        prepared_by=preparer.name if preparer else "",
        generated_on=report.generated_at.date(),
        audience=audience,
        summary=report.summary,
        content=ReportContent.model_validate(report.content),
    )
    name = f"{project.code}-{report.kind}-report-{report.generated_at.date().isoformat()}.pdf"
    return Response(
        data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# --- staff ------------------------------------------------------------------------------------


@router.get(STAFF, response_model=ReportListOut)
async def list_reports(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    kind: ReportKind | None = None,
    shared_with: Annotated[
        Audience | None, Query(description="Only reports shared with this audience.")
    ] = None,
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> ReportListOut:
    """Newest first. Project leads and Managers see every report; the client's Account
    Manager sees the ones shared with the Account Manager and their own."""
    await _project(session, user, project_id)
    reports, total = await service.list_reports(
        session,
        user,
        project_id,
        kind=kind,
        shared_with=shared_with,
        page=page,
        page_size=page_size,
    )
    return ReportListOut(
        items=await service.briefs(session, reports), total=total, page=page, page_size=page_size
    )


@router.post(STAFF, response_model=ReportOut, status_code=201)
async def generate_report(
    project_id: uuid.UUID, body: ReportSettings, user: CurrentUser, session: SessionDep
) -> ReportOut:
    """Generate report: the project's data for the type and period, kept as it is now (the
    preview). Nobody else sees it until it is shared."""
    project = await _project(session, user, project_id, writable=True)
    report = await service.generate(session, user, project, body)
    return await service.report_out(session, report, project)


@router.get(STAFF + "/{report_id}", response_model=ReportOut)
async def get_report(
    project_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ReportOut:
    project = await _project(session, user, project_id)
    report = await service.get_report(session, user, project_id, report_id)
    return await service.report_out(session, report, project)


@router.put(STAFF + "/{report_id}", response_model=ReportOut)
async def edit_report(
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    body: ReportEdit,
    user: CurrentUser,
    session: SessionDep,
) -> ReportOut:
    """Edit report: new settings, the data is generated again. 409 REPORT_SHARED while it is
    shared with anyone."""
    project = await _project(session, user, project_id, writable=True)
    report = await service.get_report(session, user, project_id, report_id)
    settings = ReportSettings.model_validate(body.model_dump(exclude={"version"}))
    report = await service.edit(session, user, project, report, settings, body.version)
    return await service.report_out(session, report, project)


@router.post(STAFF + "/{report_id}/share", response_model=ReportOut)
async def share_report(
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    body: ReportShare,
    user: CurrentUser,
    session: SessionDep,
) -> ReportOut:
    """Send report = share inside the app (no email): the full list of audiences who can
    view it (account_manager, client, manager); [] stops sharing. Newly added audiences get a
    notification. `client` needs an external project with a client."""
    project = await _project(session, user, project_id, writable=True)
    report = await service.get_report(session, user, project_id, report_id)
    report = await service.share(session, user, project, report, body.audiences, body.version)
    return await service.report_out(session, report, project)


@router.get(STAFF + "/{report_id}/pdf", response_class=Response, responses=PDF)
async def download_report(
    project_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    """Download report (A4 PDF). The footer names the audience: Internal until shared."""
    project = await _project(session, user, project_id)
    report = await service.get_report(session, user, project_id, report_id)
    audience = (
        ", ".join(AUDIENCE_LABEL[a] for a in report.shared_with) if report.shared_with else ""
    ) or "Internal"
    return await _pdf_response(session, report, project, audience)


@router.delete(STAFF + "/{report_id}", status_code=204)
async def archive_report(
    project_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Delete = archive: gone from every list, also for the people it was shared with."""
    await _project(session, user, project_id, writable=True)
    report = await service.get_report(session, user, project_id, report_id)
    await service.archive(session, user, report)


# --- client portal ----------------------------------------------------------------------------


@router.get(CLIENT, response_model=ClientReportListOut)
async def client_list(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ClientReportListOut:
    """Generated reports the project team shared with the client portal, newest share first."""
    require(user, Action.CLIENT_PORTAL)
    project = await client_service.get_project(session, user, project_id)
    items = await service.client_reports(session, project)
    return ClientReportListOut(items=items, total=len(items))


@router.get(CLIENT + "/{report_id}", response_model=ClientReportDetail)
async def client_get(
    project_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ClientReportDetail:
    require(user, Action.CLIENT_PORTAL)
    project = await client_service.get_project(session, user, project_id)
    _, detail = await service.client_report(session, project, report_id)
    return detail


@router.get(CLIENT + "/{report_id}/pdf", response_class=Response, responses=PDF)
async def client_pdf(
    project_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    require(user, Action.CLIENT_PORTAL)
    project = await client_service.get_project(session, user, project_id)
    report, _ = await service.client_report(session, project, report_id)
    return await _pdf_response(session, report, project, "Client")
