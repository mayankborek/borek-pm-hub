"""Reading the audit log (administrator only). There is no way to change it."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.audit import service
from app.audit.schemas import AuditEventListOut
from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require
from app.common.validation import PageParam, PageSizeParam
from app.core.database import SessionDep

router = APIRouter(prefix="/admin/audit-events", tags=["admin"])


@router.get("", response_model=AuditEventListOut)
async def list_audit_events(
    actor: CurrentUser,
    session: SessionDep,
    actor_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=50)] = None,
    entity_type: Annotated[str | None, Query(max_length=30)] = None,
    entity_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> AuditEventListOut:
    """Who changed what, newest first."""
    require(actor, Action.AUDIT_VIEW)
    items, total = await service.list_events(
        session,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        from_at=from_at,
        to_at=to_at,
        page=page,
        page_size=page_size,
    )
    return AuditEventListOut(items=items, total=total, page=page, page_size=page_size)
