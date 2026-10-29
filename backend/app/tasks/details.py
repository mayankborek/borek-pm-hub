"""Comments, attachments and history of a task. Routers check access; this checks data rules."""

import uuid
from datetime import UTC, datetime
from pathlib import PurePath
from urllib.parse import urlsplit

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AttachmentKind, GlobalRole
from app.common.validation import has_control_chars
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
    """Oldest first; at most the newest MAX_LIST_ITEMS."""
    rows = await session.execute(
        select(TaskComment, User)
        .join(User, User.id == TaskComment.author_id)
        .where(TaskComment.task_id == task_id, TaskComment.archived_at.is_(None))
        .order_by(TaskComment.created_at.desc(), TaskComment.id.desc())
        .limit(MAX_LIST_ITEMS)
    )
    return [_comment_out(comment, author) for comment, author in reversed(rows.all())]


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
    """Oldest first; at most the newest MAX_LIST_ITEMS."""
    rows = await session.execute(
        select(TaskAttachment, User)
        .join(User, User.id == TaskAttachment.uploaded_by)
        .where(TaskAttachment.task_id == task_id, TaskAttachment.archived_at.is_(None))
        .order_by(TaskAttachment.created_at.desc(), TaskAttachment.id.desc())
        .limit(MAX_LIST_ITEMS)
    )
    return [_attachment_out(item, uploader) for item, uploader in reversed(rows.all())]


async def get_attachment(
    session: AsyncSession, task_id: uuid.UUID, attachment_id: uuid.UUID
) -> TaskAttachment:
    item = await session.get(TaskAttachment, attachment_id)
    if item is None or item.task_id != task_id or item.archived_at is not None:
        raise AppError(404, "NOT_FOUND", "Attachment not found.")
    return item


async def add_link(session: AsyncSession, task: Task, user: User, data: LinkIn) -> AttachmentOut:
    name = (data.name or urlsplit(data.url).hostname or "link")[:255]
    item = TaskAttachment(
        task_id=task.id,
        kind=AttachmentKind.LINK.value,
        name=name,
        url=data.url,
        uploaded_by=user.id,
    )
    session.add(item)
    activity.record(session, task.id, user.id, "attachment_added", {"attachment": [None, name]})
    await session.commit()
    return _attachment_out(item, user)


# Documents, images, spreadsheets and voice notes, with the content type each is stored and
# served with. Checked on the file name; the content type the client sends is ignored, so a
# ".png" can never be served as HTML. Scripts, executables and archives are refused.
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".rtf": "application/rtf",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".aac": "audio/aac",
    ".weba": "audio/webm",
}
ALLOWED_EXTENSIONS = frozenset(CONTENT_TYPES)

# Comments and attachments lists return at most this many (the newest), so a task with a
# runaway number of them can not produce an unbounded response.
MAX_LIST_ITEMS = 500


def content_type_for(name: str) -> str:
    """The content type for a stored file name (unknown or old names: a plain download)."""
    return CONTENT_TYPES.get(PurePath(name).suffix.lower(), "application/octet-stream")


def _clean_file_name(raw: str | None) -> str:
    """Last path part, no control characters, 255 characters at most (extension kept)."""
    name = PurePath((raw or "").replace("\\", "/")).name
    name = "".join(char for char in name if not has_control_chars(char)).strip()
    if len(name) > 255:
        suffix = PurePath(name).suffix[:20]
        name = name[: 255 - len(suffix)] + suffix
    return name or "file"


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
    size = 0
    # Written to disk chunk by chunk, so a 25 MB upload never sits in memory as a whole.
    async with storage.new_file() as (storage_key, out):
        while chunk := await upload.read(CHUNK):
            size += len(chunk)
            if size > limit:
                raise AppError(
                    413,
                    "FILE_TOO_LARGE",
                    f"Files can be at most {get_settings().max_upload_mb} MB.",
                )
            await out.write(chunk)
        if size == 0:
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
        storage_key=storage_key,
        content_type=content_type_for(name),
        size_bytes=size,
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
