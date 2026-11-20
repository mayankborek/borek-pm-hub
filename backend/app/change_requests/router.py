"""Change requests of a project (staff side). Clients use /client/projects/{id}/change-requests.

Read and raise: project leads, Managers and the client's Account Managers. Fill in impact and
decide: project leads and Managers. Developers have no access.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile
from fastapi.responses import FileResponse

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action
from app.change_requests import service
from app.change_requests.models import ChangeRequestStatus
from app.change_requests.schemas import (
    AttachmentOut,
    ChangeRequestCreate,
    ChangeRequestDecision,
    ChangeRequestListOut,
    ChangeRequestOut,
    ChangeRequestUpdate,
    ChangeRequestVersion,
    CommentCreate,
    CommentOut,
)
from app.core.database import SessionDep
from app.projects.service import authorize

router = APIRouter(prefix="/projects/{project_id}/change-requests", tags=["change requests"])


@router.get("", response_model=ChangeRequestListOut)
async def list_change_requests(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    status: ChangeRequestStatus | None = None,
) -> ChangeRequestListOut:
    """Newest first, with counts per status (for the overview card)."""
    await authorize(session, user, project_id, Action.CHANGE_REQUEST_VIEW)
    requests, counts = await service.list_requests(session, project_id, status)
    return ChangeRequestListOut(
        items=await service.requests_out(session, requests), total=len(requests), counts=counts
    )


@router.post("", response_model=ChangeRequestOut, status_code=201)
async def create_change_request(
    project_id: uuid.UUID,
    body: ChangeRequestCreate,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
) -> ChangeRequestOut:
    """Starts in review and gets the next code (CR-01, CR-02 ...)."""
    await authorize(session, user, project_id, Action.CHANGE_REQUEST_SUBMIT, writable=True)
    request = await service.create_request(session, user, project_id, body)
    response.headers["Location"] = f"/api/v1/projects/{project_id}/change-requests/{request.id}"
    return (await service.requests_out(session, [request]))[0]


@router.get("/{request_id}", response_model=ChangeRequestOut)
async def get_change_request(
    project_id: uuid.UUID, request_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ChangeRequestOut:
    await authorize(session, user, project_id, Action.CHANGE_REQUEST_VIEW)
    request = await service.get_request(session, project_id, request_id)
    return (await service.requests_out(session, [request]))[0]


@router.patch("/{request_id}", response_model=ChangeRequestOut)
async def update_change_request(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    body: ChangeRequestUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> ChangeRequestOut:
    """While open (pending or in review): correct it and fill in the impact (409
    CHANGE_REQUEST_CLOSED once decided)."""
    await authorize(session, user, project_id, Action.CHANGE_REQUEST_DECIDE, writable=True)
    request = await service.update_request(session, user, project_id, request_id, body)
    return (await service.requests_out(session, [request]))[0]


@router.post("/{request_id}/start-review", response_model=ChangeRequestOut)
async def start_review(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    body: ChangeRequestVersion,
    user: CurrentUser,
    session: SessionDep,
) -> ChangeRequestOut:
    """pending -> in_review (409 NOT_PENDING otherwise)."""
    await authorize(session, user, project_id, Action.CHANGE_REQUEST_DECIDE, writable=True)
    request = await service.start_review(session, user, project_id, request_id, body.version)
    return (await service.requests_out(session, [request]))[0]


@router.post("/{request_id}/decision", response_model=ChangeRequestOut)
async def decide_change_request(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    body: ChangeRequestDecision,
    user: CurrentUser,
    session: SessionDep,
) -> ChangeRequestOut:
    """Approve or decline an in-review request (409 REVIEW_NOT_STARTED while pending); final.
    Approving a request with a milestone and a requested date moves the milestone to that date
    (it then shows as revised)."""
    await authorize(session, user, project_id, Action.CHANGE_REQUEST_DECIDE, writable=True)
    request = await service.decide(session, user, project_id, request_id, body)
    return (await service.requests_out(session, [request]))[0]


# --- conversation -------------------------------------------------------------------------------


@router.get("/{request_id}/comments", response_model=list[CommentOut])
async def list_comments(
    project_id: uuid.UUID, request_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[CommentOut]:
    """Oldest first: the shared conversation and the team's internal notes (`internal`)."""
    await authorize(session, user, project_id, Action.CHANGE_REQUEST_VIEW)
    request = await service.get_request(session, project_id, request_id)
    return await service.comments_out(session, request.id, include_internal=True)


@router.post("/{request_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    body: CommentCreate,
    user: CurrentUser,
    session: SessionDep,
) -> CommentOut:
    """`internal: true` = a note only the project team sees; otherwise the client sees it."""
    await authorize(session, user, project_id, Action.CHANGE_REQUEST_SUBMIT, writable=True)
    request = await service.get_request(session, project_id, request_id)
    return await service.add_comment(session, user, request, body.body, internal=body.internal)


@router.get("/{request_id}/attachments", response_model=list[AttachmentOut])
async def list_attachments(
    project_id: uuid.UUID, request_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[AttachmentOut]:
    await authorize(session, user, project_id, Action.CHANGE_REQUEST_VIEW)
    request = await service.get_request(session, project_id, request_id)
    return await service.attachments_out(session, request.id)


@router.post("/{request_id}/attachments", response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="multipart/form-data field 'file'")],
    user: CurrentUser,
    session: SessionDep,
) -> AttachmentOut:
    """Same rules as task files (types, MAX_UPLOAD_MB). The client sees every attachment."""
    await authorize(session, user, project_id, Action.CHANGE_REQUEST_SUBMIT, writable=True)
    request = await service.get_request(session, project_id, request_id)
    return await service.add_attachment(session, user, request, file)


@router.get("/{request_id}/attachments/{attachment_id}/download")
async def download_attachment(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    attachment_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
) -> FileResponse:
    await authorize(session, user, project_id, Action.CHANGE_REQUEST_VIEW)
    request = await service.get_request(session, project_id, request_id)
    return service.file_response(await service.get_attachment(session, request.id, attachment_id))
