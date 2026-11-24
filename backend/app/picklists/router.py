"""Picklists (BB-27). Everyone on staff reads them (for dropdowns); the administrator adds,
renames, reorders and hides values of the editable lists. Protected lists (workflow values) are
read-only: 409 PICKLIST_PROTECTED. Every change is in the audit log."""

import uuid

from fastapi import APIRouter

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, can, require
from app.core.database import SessionDep
from app.core.errors import AppError
from app.picklists import service
from app.picklists.schemas import (
    PicklistOut,
    PicklistValueIn,
    PicklistValueOut,
    PicklistValueUpdate,
)

router = APIRouter(tags=["picklists"])


@router.get("/picklists", response_model=list[PicklistOut])
async def list_picklists(user: CurrentUser, session: SessionDep) -> list[PicklistOut]:
    """Active values for dropdowns. The administrator also gets hidden values."""
    admin = can(user, Action.PICKLIST_MANAGE)
    if not admin and not can(user, Action.PROJECT_LIST):
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    return await service.list_picklists(session, include_inactive=admin)


@router.post("/admin/picklists/{key}/values", response_model=PicklistValueOut, status_code=201)
async def add_value(
    key: str, body: PicklistValueIn, user: CurrentUser, session: SessionDep
) -> PicklistValueOut:
    """Added at the end. 409 DUPLICATE_VALUE when the list has it already (any letter case)."""
    require(user, Action.PICKLIST_MANAGE)
    return await service.add_value(session, user, service.check_key(key), body)


@router.patch("/admin/picklists/{key}/values/{value_id}", response_model=PicklistValueOut)
async def update_value(
    key: str,
    value_id: uuid.UUID,
    body: PicklistValueUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> PicklistValueOut:
    """Rename, move (`position`) or hide (`is_active: false`); values are never deleted."""
    require(user, Action.PICKLIST_MANAGE)
    return await service.update_value(session, user, service.check_key(key), value_id, body)
