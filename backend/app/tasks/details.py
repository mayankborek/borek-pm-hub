"""Comments, attachments and history of a task. Routers check access; this checks data rules."""

import uuid
from datetime import UTC, datetime
from pathlib import PurePath

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AttachmentKind, GlobalRole
from app.core import storage
from app.core.config import get_settings
from app.core.errors import AppError
from app.tasks import activity
from app.tasks.details_schemas import (
    ActivityOut,
    AttachmentOut,
    CommentOut,
    LinkIn,
)
from app.tasks.models import Task, TaskActivity, TaskAttachment, TaskComment
from app.tasks.schemas import UserBrief
from app.users.models import User

CHUNK = 1024 * 1024


def _brief(user: User) -> UserBrief:
    return UserBrief(id=user.id, name=user.name, email=user.email)


def _forbidden() -> AppError:
    return AppError(403, "FORBIDDEN", "You do not have permission to do this.")


# --- history ----------------------------------------------------------------------------------


async def list_activity(
    session: AsyncSession, task_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[ActivityOut], int]:
    total = (
        await session.scalar(
            select(func.count(TaskActivity.id)).where(TaskActivity.task_id == task_id)
        )
        or 0
    )
    rows = await session.execute(
        select(TaskActivity, User)
        .join(User, User.id == TaskActivity.actor_id)
        .where(TaskActivity.task_id == task_id)
        .order_by(TaskActivity.created_at.desc(), TaskActivity.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    items = [
        ActivityOut(
            id=row.id,
            action=row.action,
            actor=_brief(actor),
            changes=row.changes,
            created_at=row.created_at,
        )
        for row, actor in rows.all()
    ]
    return items, total


# --- comments ---------------------------------------------------------------------------------


def _comment_out(comment: TaskComment, author: User) -> CommentOut:
    return CommentOut(
        id=comment.id,
        task_id=comment.task_id,
        author=_brief(author),
        body=comment.body,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
    )


async def list_comments(session: AsyncSession, task_id: uuid.UUID) -> list[CommentOut]:
    rows = await session.execute(
        select(TaskComment, User)
        .join(User, User.id == TaskComment.author_id)
        .where(TaskComment.task_id == task_id, TaskComment.archived_at.is_(None))
        .order_by(TaskComment.created_at, TaskComment.id)
    )
    return [_comment_out(comment, author) for comment, author in rows.all()]


async def _get_comment(
    session: AsyncSession, task_id: uuid.UUID, comment_id: uuid.UUID
) -> TaskComment:
    comment = await session.get(TaskComment, comment_id)
    if comment is None or comment.task_id != task_id or comment.archived_at is not None:
        raise AppError(404, "NOT_FOUND", "Comment not found.")
    return comment


async def add_comment(session: AsyncSession, task: Task, user: User, body: str) -> CommentOut:
    comment = TaskComment(task_id=task.id, author_id=user.id, body=body)
    session.add(comment)
    activity.record(session, task.id, user.id, "commented")
    await session.commit()
    return _comment_out(comment, user)


async def edit_comment(
    session: AsyncSession, task_id: uuid.UUID, comment_id: uuid.UUID, user: User, body: str
) -> CommentOut:
    comment = await _get_comment(session, task_id, comment_id)
    if comment.author_id != user.id:
        raise _forbidden()  # even a PM may not put words in someone else's mouth
    comment.body = body
    comment.edited_at = datetime.now(UTC)
    await session.commit()
    return _comment_out(comment, user)


async def archive_comment(
    session: AsyncSession, task_id: uuid.UUID, comment_id: uuid.UUID, user: User
) -> None:
    comment = await _get_comment(session, task_id, comment_id)
    if comment.author_id != user.id and user.global_role != GlobalRole.PM:
        raise _forbidden()
    comment.archived_at = datetime.now(UTC)
    await session.commit()


# --- attachments ------------------------------------------------------------------------------


def _attachment_out(item: TaskAttachment, uploader: User) -> AttachmentOut:
    is_file = item.kind == AttachmentKind.FILE.value
    return AttachmentOut(
        id=item.id,
        task_id=item.task_id,
        kind=item.kind,
        name=item.name,
        url=item.url,
        download_url=f"/api/v1/tasks/{item.task_id}/attachments/{item.id}/download"
        if is_file
        else None,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        uploaded_by=_brief(uploader),
        created_at=item.created_at,
    )


async def list_attachments(session: AsyncSession, task_id: uuid.UUID) -> list[AttachmentOut]:
    rows = await session.execute(
        select(TaskAttachment, User)
        .join(User, User.id == TaskAttachment.uploaded_by)
        .where(TaskAttachment.task_id == task_id, TaskAttachment.archived_at.is_(None))
        .order_by(TaskAttachment.created_at, TaskAttachment.id)
    )
    return [_attachment_out(item, uploader) for item, uploader in rows.all()]


async def get_attachment(
    session: AsyncSession, task_id: uuid.UUID, attachment_id: uuid.UUID
) -> TaskAttachment:
    item = await session.get(TaskAttachment, attachment_id)
    if item is None or item.task_id != task_id or item.archived_at is not None:
        raise AppError(404, "NOT_FOUND", "Attachment not found.")
    return item


async def add_link(session: AsyncSession, task: Task, user: User, data: LinkIn) -> AttachmentOut:
    name = data.name or (data.url.split("//", 1)[1].split("/", 1)[0])
    item = TaskAttachment(
        task_id=task.id,
        kind=AttachmentKind.LINK.value,
        name=name[:255],
        url=data.url,
        uploaded_by=user.id,
    )
    session.add(item)
    activity.record(session, task.id, user.id, "attachment_added", {"attachment": [None, name]})
    await session.commit()
    return _attachment_out(item, user)


# Documents, images, spreadsheets and voice notes. Checked on the file name, never on the
# content type the client sends. Scripts, executables and archives are refused.
ALLOWED_EXTENSIONS = frozenset(
    {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".txt", ".md", ".rtf",
        ".odt", ".ods", ".png", ".jpg", ".jpeg", ".gif", ".webp",
        ".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".weba",
    }
)  # fmt: skip


def _clean_file_name(raw: str | None) -> str:
    name = PurePath((raw or "").replace("\\", "/")).name.strip()
    return (name or "file")[:255]


async def add_file(
    session: AsyncSession, task: Task, user: User, upload: UploadFile
) -> AttachmentOut:
    name = _clean_file_name(upload.filename)
    if PurePath(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise AppError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            "This file type is not allowed. Use documents, spreadsheets, images, PDFs, "
            "text files or audio recordings.",
        )
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = bytearray()
    while chunk := await upload.read(CHUNK):
        data += chunk
        if len(data) > limit:
            raise AppError(
                413, "FILE_TOO_LARGE", f"Files can be at most {get_settings().max_upload_mb} MB."
            )
    if not data:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The request is not valid.",
            [{"field": "file", "issue": "empty", "message": "The file is empty."}],
        )
    item = TaskAttachment(
        task_id=task.id,
        kind=AttachmentKind.FILE.value,
        name=name,
        storage_key=await storage.save(bytes(data)),
        content_type=(upload.content_type or "application/octet-stream")[:150],
        size_bytes=len(data),
        uploaded_by=user.id,
    )
    session.add(item)
    activity.record(session, task.id, user.id, "attachment_added", {"attachment": [None, name]})
    await session.commit()
    return _attachment_out(item, user)


async def archive_attachment(
    session: AsyncSession, task_id: uuid.UUID, attachment_id: uuid.UUID, user: User
) -> None:
    """Hide the attachment. The stored file is kept (nothing is physically deleted)."""
    item = await get_attachment(session, task_id, attachment_id)
    if item.uploaded_by != user.id and user.global_role != GlobalRole.PM:
        raise _forbidden()
    item.archived_at = datetime.now(UTC)
    activity.record(
        session, task_id, user.id, "attachment_removed", {"attachment": [item.name, None]}
    )
    await session.commit()
