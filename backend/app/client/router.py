"""Client portal (/client/...): read-only views for client contacts.

Every route needs `CLIENT_PORTAL`, which only active client contacts have, and shows only the
external, not archived projects of the client's own organisation (404 for anything else).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile
from fastapi.responses import FileResponse

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require
from app.change_requests.schemas import ChangeRequestCreate, ClientCommentCreate
from app.client import service
from app.client.pdf import build_report_pdf
from app.client.schemas import (
    ClientAttachmentOut,
    ClientChangeRequestListOut,
    ClientChangeRequestOut,
    ClientCommentOut,
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


@router.get("/projects/{project_id}/change-requests", response_model=ClientChangeRequestListOut)
async def list_change_requests(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ClientChangeRequestListOut:
    """The project's change requests, newest first, with counts per status."""
    require(user, Action.CLIENT_PORTAL)
    return await service.list_change_requests(session, user, project_id)


@router.post(
    "/projects/{project_id}/change-requests",
    response_model=ClientChangeRequestOut,
    status_code=201,
)
async def submit_change_request(
    project_id: uuid.UUID, body: ChangeRequestCreate, user: CurrentUser, session: SessionDep
) -> ClientChangeRequestOut:
    """Raise a request. To move a milestone, send its id (one shown to you) and the new date."""
    require(user, Action.CLIENT_PORTAL)
    return await service.submit_change_request(session, user, project_id, body)


@router.get(
    "/projects/{project_id}/change-requests/{request_id}", response_model=ClientChangeRequestOut
)
async def get_change_request(
    project_id: uuid.UUID, request_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ClientChangeRequestOut:
    require(user, Action.CLIENT_PORTAL)
    return await service.get_change_request(session, user, project_id, request_id)


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


CR_PATH = "/projects/{project_id}/change-requests/{request_id}"


@router.get(f"{CR_PATH}/comments", response_model=list[ClientCommentOut])
async def list_change_request_comments(
    project_id: uuid.UUID, request_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[ClientCommentOut]:
    """The shared conversation, oldest first (internal team notes never appear)."""
    require(user, Action.CLIENT_PORTAL)
    return await service.list_comments(session, user, project_id, request_id)


@router.post(f"{CR_PATH}/comments", response_model=ClientCommentOut, status_code=201)
async def add_change_request_comment(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    body: ClientCommentCreate,
    user: CurrentUser,
    session: SessionDep,
) -> ClientCommentOut:
    require(user, Action.CLIENT_PORTAL)
    return await service.add_comment(session, user, project_id, request_id, body.body)


@router.get(f"{CR_PATH}/attachments", response_model=list[ClientAttachmentOut])
async def list_change_request_attachments(
    project_id: uuid.UUID, request_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[ClientAttachmentOut]:
    require(user, Action.CLIENT_PORTAL)
    return await service.list_attachments(session, user, project_id, request_id)


@router.post(f"{CR_PATH}/attachments", response_model=ClientAttachmentOut, status_code=201)
async def upload_change_request_attachment(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="multipart/form-data field 'file'")],
    user: CurrentUser,
    session: SessionDep,
) -> ClientAttachmentOut:
    """Allowed: documents, spreadsheets, images, PDFs, text, audio; at most MAX_UPLOAD_MB."""
    require(user, Action.CLIENT_PORTAL)
    return await service.add_attachment(session, user, project_id, request_id, file)


@router.get(f"{CR_PATH}/attachments/{{attachment_id}}/download")
async def download_change_request_attachment(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    attachment_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
) -> FileResponse:
    require(user, Action.CLIENT_PORTAL)
    return await service.download_attachment(session, user, project_id, request_id, attachment_id)
