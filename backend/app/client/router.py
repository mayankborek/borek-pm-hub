"""Client portal (/client/...): read-only views for client contacts.

Every route needs `CLIENT_PORTAL`, which only active client contacts have, and shows only the
external, not archived projects of the client's own organisation (404 for anything else).
"""

import uuid

from fastapi import APIRouter, Response

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require
from app.client import service
from app.client.pdf import build_report_pdf
from app.client.schemas import (
    ClientPortalOut,
    ClientProjectDetailOut,
    ClientReportOut,
    ClientRoadmapOut,
)
from app.core.database import SessionDep

router = APIRouter(prefix="/client", tags=["client"])


@router.get("/portal", response_model=ClientPortalOut)
async def get_portal(user: CurrentUser, session: SessionDep) -> ClientPortalOut:
    """Dashboard and project list: the organisation, its projects with published health and
    progress, the newest published reports and a health summary."""
    require(user, Action.CLIENT_PORTAL)
    return await service.portal(session, user)


@router.get("/projects/{project_id}", response_model=ClientProjectDetailOut)
async def get_project(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ClientProjectDetailOut:
    """Project overview with its contacts and published reports."""
    require(user, Action.CLIENT_PORTAL)
    return await service.project_detail(session, user, project_id)


@router.get("/projects/{project_id}/roadmap", response_model=ClientRoadmapOut)
async def get_roadmap(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ClientRoadmapOut:
    """The project roadmap: visible phases (bars with status and completed share) and visible
    milestones (diamonds with state), plus the date range and today."""
    require(user, Action.CLIENT_PORTAL)
    return await service.project_roadmap(session, user, project_id)


@router.get("/projects/{project_id}/reports/{report_id}", response_model=ClientReportOut)
async def get_report(
    project_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ClientReportOut:
    require(user, Action.CLIENT_PORTAL)
    return await service.get_report(session, user, project_id, report_id)


@router.get(
    "/projects/{project_id}/reports/{report_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {"schema": {"type": "string"}}}}},
)
async def download_report(
    project_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    """The published report as a PDF file."""
    require(user, Action.CLIENT_PORTAL)
    report = await service.get_report(session, user, project_id, report_id)
    filename = f"status-report-{report.report_date.isoformat()}.pdf"
    return Response(
        build_report_pdf(report),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
