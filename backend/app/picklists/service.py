"""Picklists: editable lists in the database, protected workflow lists from the code."""

import uuid
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.change_requests.models import ChangeRequestStatus
from app.common.enums import (
    ProjectStatus,
    ProjectType,
    RaciRole,
    StakeholderInfluence,
    StatusCategory,
    TaskPriority,
)
from app.core.errors import AppError
from app.picklists.models import PicklistKey, PicklistValue
from app.picklists.schemas import (
    PicklistOut,
    PicklistValueIn,
    PicklistValueOut,
    PicklistValueUpdate,
)
from app.registers.models import Level
from app.requirements.models import RequirementStatus
from app.users.models import User

EDITABLE: dict[PicklistKey, str] = {
    PicklistKey.PROJECT_CATEGORY: "Project category",
    PicklistKey.COMMUNICATION_ROLE: "Stakeholder communication role",
}
PROTECTED: dict[str, tuple[str, type[StrEnum]]] = {
    "task_priority": ("Task priority", TaskPriority),
    "task_status_category": ("Task status category", StatusCategory),
    "project_status": ("Project status", ProjectStatus),
    "project_type": ("Project type", ProjectType),
    "change_request_status": ("Change request status", ChangeRequestStatus),
    "requirement_status": ("Requirement status", RequirementStatus),
    "stakeholder_influence": ("Stakeholder influence", StakeholderInfluence),
    "raci_role": ("RACI role", RaciRole),
    "risk_level": ("Risk probability / impact", Level),
}


def check_key(key: str) -> PicklistKey:
    if key in PROTECTED:
        raise AppError(
            409,
            "PICKLIST_PROTECTED",
            "This list holds workflow values and cannot be changed here.",
        )
    try:
        return PicklistKey(key)
    except ValueError:
        raise AppError(404, "NOT_FOUND", "Picklist not found.") from None


def _out(v: PicklistValue) -> PicklistValueOut:
    return PicklistValueOut(
        id=v.id, value=v.value, position=v.position, is_active=v.is_active, version=v.version
    )


async def list_picklists(session: AsyncSession, *, include_inactive: bool) -> list[PicklistOut]:
    query = select(PicklistValue).order_by(PicklistValue.position, PicklistValue.value)
    if not include_inactive:
        query = query.where(PicklistValue.is_active.is_(True))
    rows = list(await session.scalars(query))
    lists = [
        PicklistOut(
            key=key.value,
            label=label,
            protected=False,
            values=[_out(v) for v in rows if v.list_key == key.value],
        )
        for key, label in EDITABLE.items()
    ]
    lists += [
        PicklistOut(
            key=key,
            label=label,
            protected=True,
            values=[
                PicklistValueOut(id=None, value=str(m), position=i, is_active=True, version=None)
                for i, m in enumerate(enum, start=1)
            ],
        )
        for key, (label, enum) in PROTECTED.items()
    ]
    return lists


async def active_values(session: AsyncSession, key: PicklistKey) -> list[str]:
    return list(
        await session.scalars(
            select(PicklistValue.value)
            .where(PicklistValue.list_key == key.value, PicklistValue.is_active.is_(True))
            .order_by(PicklistValue.position, PicklistValue.value)
        )
    )


def _duplicate() -> AppError:
    return AppError(409, "DUPLICATE_VALUE", "This list already has that value.")


async def _check_unique(
    session: AsyncSession, key: PicklistKey, value: str, skip: uuid.UUID | None = None
) -> None:
    query = select(PicklistValue.id).where(
        PicklistValue.list_key == key.value, func.lower(PicklistValue.value) == value.lower()
    )
    if skip is not None:
        query = query.where(PicklistValue.id != skip)
    if await session.scalar(query) is not None:
        raise _duplicate()


def _stale() -> AppError:
    return AppError(409, "VERSION_CONFLICT", "The value was changed by someone else. Reload.")


async def add_value(
    session: AsyncSession, actor: User, key: PicklistKey, data: PicklistValueIn
) -> PicklistValueOut:
    await _check_unique(session, key, data.value)
    last = await session.scalar(
        select(func.max(PicklistValue.position)).where(PicklistValue.list_key == key.value)
    )
    item = PicklistValue(
        list_key=key.value, value=data.value, position=(last or 0) + 1, created_by=actor.id
    )
    session.add(item)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise _duplicate() from None
    record_audit(
        session,
        actor,
        "picklist.value_added",
        "picklist",
        item.id,
        after={"list": key.value, "value": item.value},
    )
    await session.commit()
    await session.refresh(item)
    return _out(item)


async def update_value(
    session: AsyncSession,
    actor: User,
    key: PicklistKey,
    value_id: uuid.UUID,
    data: PicklistValueUpdate,
) -> PicklistValueOut:
    item = await session.get(PicklistValue, value_id, populate_existing=True)
    if item is None or item.list_key != key.value:
        raise AppError(404, "NOT_FOUND", "Value not found.")
    if data.version != item.version:
        raise _stale()
    if data.value is not None:
        await _check_unique(session, key, data.value, skip=item.id)
    before = {"value": item.value, "position": item.position, "is_active": item.is_active}
    changes = data.model_dump(exclude={"version"}, exclude_unset=True)
    for field, value in changes.items():
        setattr(item, field, value)
    record_audit(
        session,
        actor,
        "picklist.value_changed",
        "picklist",
        item.id,
        before={"list": key.value, **{k: before[k] for k in changes}},
        after={"list": key.value, **changes},
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _duplicate() from None
    except StaleDataError:
        await session.rollback()
        raise _stale() from None
    await session.refresh(item)
    return _out(item)
