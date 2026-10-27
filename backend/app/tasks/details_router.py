"""Task details endpoints: history, comments, attachments (F08)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action
from app.common.enums import AttachmentKind
from app.core import storage
from app.core.database import SessionDep
from app.core.errors import AppError
from app.tasks import details
from app.tasks.details_schemas import (
    ActivityListOut,
    AttachmentOut,
    CommentIn,
    CommentOut,
    LinkIn,
)
from app.tasks.router import _task_for

router = APIRouter(prefix="/tasks/{task_id}", tags=["task details"])


# --- history ----------------------------------------------------------------------------------


@router.get("/activity", response_model=ActivityListOut)
async def list_activity(
    task_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ActivityListOut:
    """Who changed what and when, newest first."""
    await _task_for(session, user, task_id, Action.TASK_VIEW)
    items, total = await details.list_activity(session, task_id, page, page_size)
    return ActivityListOut(items=items, total=total, page=page, page_size=page_size)


# --- comments ---------------------------------------------------------------------------------


@router.get("/comments", response_model=list[CommentOut])
async def list_comments(
    task_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[CommentOut]:
    await _task_for(session, user, task_id, Action.TASK_VIEW)
    return await details.list_comments(session, task_id)


@router.post("/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    task_id: uuid.UUID, body: CommentIn, user: CurrentUser, session: SessionDep
) -> CommentOut:
    task = await _task_for(session, user, task_id, Action.TASK_COMMENT, writable=True)
    return await details.add_comment(session, task, user, body.body)


@router.patch("/comments/{comment_id}", response_model=CommentOut)
async def edit_comment(
    task_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: CommentIn,
    user: CurrentUser,
    session: SessionDep,
) -> CommentOut:
    """Only the author can edit a comment."""
    await _task_for(session, user, task_id, Action.TASK_COMMENT, writable=True)
    return await details.edit_comment(session, task_id, comment_id, user, body.body)


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    task_id: uuid.UUID, comment_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Archive a comment. The author or a PM can."""
    await _task_for(session, user, task_id, Action.TASK_COMMENT, writable=True)
    await details.archive_comment(session, task_id, comment_id, user)


# --- attachments ------------------------------------------------------------------------------


@router.get("/attachments", response_model=list[AttachmentOut])
async def list_attachments(
    task_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[AttachmentOut]:
    await _task_for(session, user, task_id, Action.TASK_VIEW)
    return await details.list_attachments(session, task_id)


@router.post("/attachments", response_model=AttachmentOut, status_code=201)
async def upload_file(
    task_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    file: Annotated[UploadFile, File(description="multipart/form-data field 'file'")],
) -> AttachmentOut:
    """Upload a file (size limit MAX_UPLOAD_MB, default 25 MB)."""
    task = await _task_for(session, user, task_id, Action.TASK_COMMENT, writable=True)
    return await details.add_file(session, task, user, file)


@router.post("/attachments/link", response_model=AttachmentOut, status_code=201)
async def add_link(
    task_id: uuid.UUID, body: LinkIn, user: CurrentUser, session: SessionDep
) -> AttachmentOut:
    """Attach a link (for example a SharePoint document) instead of a file."""
    task = await _task_for(session, user, task_id, Action.TASK_COMMENT, writable=True)
    return await details.add_link(session, task, user, body)


@router.get("/attachments/{attachment_id}/download")
async def download_file(
    task_id: uuid.UUID, attachment_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> FileResponse:
    """Download a stored file. Anyone who can see the task can download it."""
    await _task_for(session, user, task_id, Action.TASK_VIEW)
    item = await details.get_attachment(session, task_id, attachment_id)
    if item.kind != AttachmentKind.FILE.value or item.storage_key is None:
        raise AppError(404, "NOT_FOUND", "Attachment not found.")
    path = storage.path_for(item.storage_key)
    if not path.is_file():
        raise AppError(404, "FILE_MISSING", "The stored file is missing.")
    return FileResponse(
        path,
        media_type=item.content_type or "application/octet-stream",
        filename=item.name,  # sent as an attachment, never shown inline
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    task_id: uuid.UUID, attachment_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Archive an attachment. The uploader or a PM can."""
    await _task_for(session, user, task_id, Action.TASK_COMMENT, writable=True)
    await details.archive_attachment(session, task_id, attachment_id, user)
