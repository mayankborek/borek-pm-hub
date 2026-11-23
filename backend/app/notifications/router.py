"""The signed-in person's notifications (every role, clients included).

The frontend polls `unread-count` (every 30-60 seconds is enough) and loads the list when the
panel opens. Each item links to its item (`entity_type`, `entity_id`, `project`); the target
route checks access again.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.auth.dependencies import CurrentUser
from app.core.database import SessionDep
from app.notifications import service
from app.notifications.schemas import (
    NotificationListOut,
    ReadAllOut,
    SettingsOut,
    SettingsUpdate,
    UnreadCountOut,
)

router = APIRouter(prefix="/me", tags=["notifications"])


@router.get("/notifications", response_model=NotificationListOut)
async def list_notifications(
    user: CurrentUser,
    session: SessionDep,
    unread: bool = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE)] = 20,
) -> NotificationListOut:
    """Newest first. `unread=true` for unread only; `cursor` = `next_cursor` of the previous
    page."""
    items, next_cursor = await service.list_notifications(
        session, user, unread_only=unread, cursor=cursor, limit=limit
    )
    return NotificationListOut(
        items=items, next_cursor=next_cursor, unread_count=await service.unread_count(session, user)
    )


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
async def unread_count(user: CurrentUser, session: SessionDep) -> UnreadCountOut:
    """For the bell badge. Cheap: poll it."""
    return UnreadCountOut(unread=await service.unread_count(session, user))


@router.post("/notifications/read-all", response_model=ReadAllOut)
async def read_all(user: CurrentUser, session: SessionDep) -> ReadAllOut:
    return ReadAllOut(marked=await service.mark_all_read(session, user))


@router.post("/notifications/{notification_id}/read", status_code=204)
async def read_one(notification_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    """Idempotent. 404 for someone else's notification."""
    await service.mark_read(session, user, notification_id)
    return Response(status_code=204)


@router.get("/notification-settings", response_model=SettingsOut)
async def get_settings(user: CurrentUser, session: SessionDep) -> SettingsOut:
    """The settings for your role, all on until switched off."""
    return SettingsOut(settings=await service.get_settings(session, user))


@router.put("/notification-settings", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate, user: CurrentUser, session: SessionDep
) -> SettingsOut:
    """Switch settings on or off; send only the keys that change (422 unknown_setting for keys
    that are not yours)."""
    return SettingsOut(settings=await service.update_settings(session, user, body.settings))
