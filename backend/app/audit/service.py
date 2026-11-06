"""Writing and reading the audit log. Never pass passwords or invite tokens in `before`/`after`."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.audit.schemas import AuditEventOut, AuditPerson
from app.core.middleware import request_id_ctx
from app.users.models import User


def record_audit(
    session: AsyncSession,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    *,
    project_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Add one event to the session: it is saved, or undone, together with the change itself."""
    request_id = request_id_ctx.get()
    session.add(
        AuditEvent(
            actor_id=actor.id if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=project_id,
            before=before,
            after=after,
            request_id=None if request_id == "-" else request_id,
        )
    )


async def list_events(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str | None,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    from_at: datetime | None,
    to_at: datetime | None,
    page: int,
    page_size: int,
) -> tuple[list[AuditEventOut], int]:
    """Newest first. Actor names come from the current user row."""
    conditions: list[ColumnElement[bool]] = []
    if actor_id:
        conditions.append(AuditEvent.actor_id == actor_id)
    if action:
        conditions.append(AuditEvent.action == action)
    if entity_type:
        conditions.append(AuditEvent.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditEvent.entity_id == entity_id)
    if project_id:
        conditions.append(AuditEvent.project_id == project_id)
    if from_at:
        conditions.append(AuditEvent.at >= from_at)
    if to_at:
        conditions.append(AuditEvent.at <= to_at)
    total = await session.scalar(select(func.count(AuditEvent.id)).where(*conditions)) or 0
    rows = await session.execute(
        select(AuditEvent, User)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(*conditions)
        .order_by(AuditEvent.at.desc(), AuditEvent.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        AuditEventOut(
            id=event.id,
            at=event.at,
            actor=AuditPerson(id=user.id, name=user.name, email=user.email) if user else None,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            project_id=event.project_id,
            before=event.before,
            after=event.after,
            request_id=event.request_id,
        )
        for event, user in rows.all()
    ]
    return items, total
