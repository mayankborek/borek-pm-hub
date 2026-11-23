"""Change requests. Routers check permissions; rules live here.

A request starts pending. The project lead (or a Manager) starts the review, then decides
(approved or declined). It can change while open (pending or in review); a decision is final.
Approving a request with a milestone and a requested date moves that milestone's
due date and keeps the date it had before, which makes the milestone "revised".
"""

import uuid
from collections import Counter
from datetime import UTC, datetime

from fastapi import UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.auth.permissions import is_client
from app.change_requests.models import (
    ChangeRequest,
    ChangeRequestAttachment,
    ChangeRequestComment,
    ChangeRequestStatus,
)
from app.change_requests.schemas import (
    AttachmentOut,
    ChangeRequestCreate,
    ChangeRequestDecision,
    ChangeRequestOut,
    ChangeRequestUpdate,
    CommentOut,
    MilestoneBrief,
)
from app.core import storage
from app.core.errors import AppError
from app.milestones.models import Milestone
from app.notifications import events as notifications
from app.organisations.schemas import PersonBrief
from app.projects.models import Project
from app.tasks.details import content_type_for, store_upload
from app.users.models import User


def _not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Change request not found.")


def _version_conflict() -> AppError:
    return AppError(
        409, "VERSION_CONFLICT", "The change request was changed by someone else. Reload."
    )


def _closed() -> AppError:
    return AppError(
        409, "CHANGE_REQUEST_CLOSED", "The change request is already decided and cannot change."
    )


OPEN = (ChangeRequestStatus.PENDING.value, ChangeRequestStatus.IN_REVIEW.value)


def _invalid(field: str, issue: str, message: str) -> AppError:
    return AppError(
        422,
        "VALIDATION_ERROR",
        "The request is not valid.",
        [{"field": field, "issue": issue, "message": message}],
    )


async def _commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise _version_conflict() from None


# --- reading ------------------------------------------------------------------------------------


async def requests_out(
    session: AsyncSession, requests: list[ChangeRequest]
) -> list[ChangeRequestOut]:
    user_ids = {r.submitted_by for r in requests} | {r.decided_by for r in requests if r.decided_by}
    users = (
        {u.id: u for u in await session.scalars(select(User).where(User.id.in_(user_ids)))}
        if user_ids
        else {}
    )
    milestone_ids = {r.milestone_id for r in requests if r.milestone_id}
    milestones = (
        {
            m.id: m
            for m in await session.scalars(select(Milestone).where(Milestone.id.in_(milestone_ids)))
        }
        if milestone_ids
        else {}
    )

    def person(user_id: uuid.UUID | None) -> PersonBrief | None:
        user = users.get(user_id) if user_id else None
        return PersonBrief(id=user.id, name=user.name, email=user.email) if user else None

    out = []
    for r in requests:
        m = milestones.get(r.milestone_id) if r.milestone_id else None
        submitter = person(r.submitted_by)
        assert submitter is not None
        out.append(
            ChangeRequestOut(
                id=r.id,
                project_id=r.project_id,
                code=r.code,
                title=r.title,
                description=r.description,
                reason=r.reason,
                milestone=(
                    MilestoneBrief(id=m.id, code=m.code, name=m.name, due_date=m.due_date)
                    if m
                    else None
                ),
                requested_date=r.requested_date,
                status=ChangeRequestStatus(r.status),
                review_started_at=r.review_started_at,
                impact_schedule_days=r.impact_schedule_days,
                impact_effort_hours=r.impact_effort_hours,
                impact_scope=r.impact_scope,
                decision_note=r.decision_note,
                decided_by=person(r.decided_by),
                decided_at=r.decided_at,
                submitted_by=submitter,
                submitted_by_client=is_client(users[r.submitted_by]),
                version=r.version,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return out


async def list_requests(
    session: AsyncSession, project_id: uuid.UUID, status: ChangeRequestStatus | None = None
) -> tuple[list[ChangeRequest], dict[str, int]]:
    """Newest first, and counts per status over all of the project's requests."""
    rows = list(
        await session.scalars(
            select(ChangeRequest)
            .where(ChangeRequest.project_id == project_id)
            .order_by(ChangeRequest.created_at.desc(), ChangeRequest.code.desc())
        )
    )
    per_status: Counter[str] = Counter(r.status for r in rows)
    counts = {
        "total": len(rows),
        **{s.value: per_status.get(s.value, 0) for s in ChangeRequestStatus},
    }
    if status is not None:
        rows = [r for r in rows if r.status == status.value]
    return rows, counts


async def get_request(
    session: AsyncSession, project_id: uuid.UUID, request_id: uuid.UUID
) -> ChangeRequest:
    found = await session.get(ChangeRequest, request_id)
    if found is None or found.project_id != project_id:
        raise _not_found()
    return found


# --- writing ------------------------------------------------------------------------------------


async def _check_milestone(
    session: AsyncSession, project_id: uuid.UUID, milestone_id: uuid.UUID, *, for_client: bool
) -> None:
    """An active milestone of the project; a client may only pick one shown to them."""
    m = await session.get(Milestone, milestone_id)
    if (
        m is None
        or m.project_id != project_id
        or m.archived_at is not None
        or (for_client and not m.client_visible)
    ):
        raise _invalid("milestone_id", "unknown_milestone", "Pick a milestone of this project.")


async def _next_code(session: AsyncSession, project_id: uuid.UUID) -> str:
    # Lock the project row so two requests raised at once never get the same code.
    await session.execute(select(Project.id).where(Project.id == project_id).with_for_update())
    used = await session.scalar(
        select(func.count(ChangeRequest.id)).where(ChangeRequest.project_id == project_id)
    )
    return f"CR-{(used or 0) + 1:02d}"


async def create_request(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: ChangeRequestCreate
) -> ChangeRequest:
    if data.milestone_id:
        await _check_milestone(session, project_id, data.milestone_id, for_client=is_client(actor))
    request = ChangeRequest(
        project_id=project_id,
        code=await _next_code(session, project_id),
        submitted_by=actor.id,
        **data.model_dump(),
    )
    session.add(request)
    await session.flush()
    record_audit(
        session,
        actor,
        "change_request.submitted",
        "change_request",
        request.id,
        project_id=project_id,
        after={"code": request.code, "title": request.title},
    )
    await notifications.change_request_submitted(session, actor, request)
    await session.commit()
    await session.refresh(request)
    return request


async def update_request(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    data: ChangeRequestUpdate,
) -> ChangeRequest:
    request = await get_request(session, project_id, request_id)
    if request.status not in OPEN:
        raise _closed()
    if data.version != request.version:
        raise _version_conflict()
    changes = data.model_dump(exclude={"version"}, exclude_unset=True)
    if changes.get("milestone_id"):
        await _check_milestone(session, project_id, changes["milestone_id"], for_client=False)
    milestone_id = changes.get("milestone_id", request.milestone_id)
    requested_date = changes.get("requested_date", request.requested_date)
    if requested_date is not None and milestone_id is None:
        raise _invalid("requested_date", "needs_milestone", "A requested date needs a milestone.")
    for field, value in changes.items():
        setattr(request, field, value)
    record_audit(
        session,
        actor,
        "change_request.updated",
        "change_request",
        request.id,
        project_id=project_id,
        after={"changed": sorted(changes)},
    )
    await _commit(session)
    await session.refresh(request)
    return request


async def start_review(
    session: AsyncSession, actor: User, project_id: uuid.UUID, request_id: uuid.UUID, version: int
) -> ChangeRequest:
    """pending -> in_review."""
    request = await get_request(session, project_id, request_id)
    if request.status != ChangeRequestStatus.PENDING.value:
        raise AppError(409, "NOT_PENDING", "The review of this request has already started.")
    if version != request.version:
        raise _version_conflict()
    request.status = ChangeRequestStatus.IN_REVIEW.value
    request.review_started_at = datetime.now(UTC)
    record_audit(
        session,
        actor,
        "change_request.review_started",
        "change_request",
        request.id,
        project_id=project_id,
        after={"code": request.code},
    )
    await notifications.change_request_review_started(session, actor, request)
    await _commit(session)
    await session.refresh(request)
    return request


async def decide(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    data: ChangeRequestDecision,
) -> ChangeRequest:
    request = await get_request(session, project_id, request_id)
    if request.status == ChangeRequestStatus.PENDING.value:
        raise AppError(
            409, "REVIEW_NOT_STARTED", "Start the review before deciding on the request."
        )
    if request.status not in OPEN:
        raise _closed()
    if data.version != request.version:
        raise _version_conflict()
    moved: dict[str, str] | None = None
    if data.decision == ChangeRequestStatus.APPROVED.value and request.requested_date:
        assert request.milestone_id is not None  # the database guarantees it
        milestone = await session.get(Milestone, request.milestone_id)
        if milestone is None or milestone.archived_at is not None:
            raise AppError(
                409,
                "MILESTONE_ARCHIVED",
                "The milestone was archived. Clear the milestone and date, then approve.",
            )
        if milestone.completed_at is not None:
            raise AppError(
                409,
                "MILESTONE_DONE",
                "The milestone is already reached. Clear the milestone and date, then approve.",
            )
        moved = {
            "milestone": milestone.code,
            "from": milestone.due_date.isoformat(),
            "to": request.requested_date.isoformat(),
        }
        if milestone.original_due_date is None:
            milestone.original_due_date = milestone.due_date
        milestone.due_date = request.requested_date
    request.status = data.decision
    request.decision_note = data.note
    request.decided_by = actor.id
    request.decided_at = datetime.now(UTC)
    after: dict[str, object] = {"code": request.code, "decision": data.decision}
    if moved:
        after["moved"] = moved
    record_audit(
        session,
        actor,
        f"change_request.{data.decision}",
        "change_request",
        request.id,
        project_id=project_id,
        after=after,
    )
    await notifications.change_request_decided(session, actor, request)
    await _commit(session)
    await session.refresh(request)
    return request


# --- conversation: comments and attachments -------------------------------------------------------

MAX_LIST_ITEMS = 500  # at most the newest this many, so a runaway thread stays bounded


def _person(user: User) -> PersonBrief:
    return PersonBrief(id=user.id, name=user.name, email=user.email)


async def comments_out(
    session: AsyncSession, request_id: uuid.UUID, *, include_internal: bool
) -> list[CommentOut]:
    """Oldest first. Without `include_internal` (clients) the team's internal notes stay out."""
    query = (
        select(ChangeRequestComment, User)
        .join(User, User.id == ChangeRequestComment.author_id)
        .where(ChangeRequestComment.change_request_id == request_id)
    )
    if not include_internal:
        query = query.where(ChangeRequestComment.internal.is_(False))
    rows = await session.execute(
        query.order_by(ChangeRequestComment.created_at.desc(), ChangeRequestComment.id).limit(
            MAX_LIST_ITEMS
        )
    )
    return [
        CommentOut(
            id=comment.id,
            body=comment.body,
            internal=comment.internal,
            author=_person(author),
            author_is_client=is_client(author),
            created_at=comment.created_at,
        )
        for comment, author in reversed(rows.all())
    ]


async def add_comment(
    session: AsyncSession, actor: User, request: ChangeRequest, body: str, *, internal: bool
) -> CommentOut:
    """Clients can only write to the shared conversation (the router never passes internal)."""
    if internal and is_client(actor):
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    comment = ChangeRequestComment(
        change_request_id=request.id, author_id=actor.id, body=body, internal=internal
    )
    session.add(comment)
    await notifications.change_request_commented(session, actor, request, internal=internal)
    await session.commit()
    await session.refresh(comment)
    return CommentOut(
        id=comment.id,
        body=comment.body,
        internal=comment.internal,
        author=_person(actor),
        author_is_client=is_client(actor),
        created_at=comment.created_at,
    )


async def attachments_out(session: AsyncSession, request_id: uuid.UUID) -> list[AttachmentOut]:
    """Oldest first."""
    rows = await session.execute(
        select(ChangeRequestAttachment, User)
        .join(User, User.id == ChangeRequestAttachment.uploaded_by)
        .where(ChangeRequestAttachment.change_request_id == request_id)
        .order_by(ChangeRequestAttachment.created_at.desc(), ChangeRequestAttachment.id)
        .limit(MAX_LIST_ITEMS)
    )
    return [
        AttachmentOut(
            id=item.id,
            name=item.name,
            content_type=item.content_type,
            size_bytes=item.size_bytes,
            uploaded_by=_person(uploader),
            created_at=item.created_at,
        )
        for item, uploader in reversed(rows.all())
    ]


async def add_attachment(
    session: AsyncSession, actor: User, request: ChangeRequest, upload: UploadFile
) -> AttachmentOut:
    """Same rules as task files: allowed types only, MAX_UPLOAD_MB, not empty."""
    name, storage_key, size = await store_upload(upload)
    item = ChangeRequestAttachment(
        change_request_id=request.id,
        name=name,
        storage_key=storage_key,
        content_type=content_type_for(name),
        size_bytes=size,
        uploaded_by=actor.id,
    )
    session.add(item)
    record_audit(
        session,
        actor,
        "change_request.file_added",
        "change_request",
        request.id,
        project_id=request.project_id,
        after={"file": name},
    )
    await session.commit()
    await session.refresh(item)
    return AttachmentOut(
        id=item.id,
        name=item.name,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        uploaded_by=_person(actor),
        created_at=item.created_at,
    )


async def get_attachment(
    session: AsyncSession, request_id: uuid.UUID, attachment_id: uuid.UUID
) -> ChangeRequestAttachment:
    item = await session.get(ChangeRequestAttachment, attachment_id)
    if item is None or item.change_request_id != request_id:
        raise AppError(404, "NOT_FOUND", "Attachment not found.")
    return item


def file_response(item: ChangeRequestAttachment) -> FileResponse:
    path = storage.path_for(item.storage_key)
    if not path.is_file():
        raise AppError(404, "FILE_MISSING", "The stored file is missing.")
    return FileResponse(
        path,
        media_type=content_type_for(item.name),  # never the type the uploader claimed
        filename=item.name,  # always a download, never shown inline
        headers={"X-Content-Type-Options": "nosniff"},
    )
