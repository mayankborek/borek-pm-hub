"""Risks, issues and decisions of a project. Routers check permissions; rules live here."""

import uuid
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.common.enums import TaskPriority
from app.core.errors import AppError
from app.organisations.schemas import PersonBrief
from app.projects.models import Project, ProjectMember
from app.registers.models import PREFIX, STATUSES, Level, RegisterItem, RegisterKind
from app.registers.schemas import (
    KIND_FIELDS,
    RegisterCreate,
    RegisterFields,
    RegisterItemOut,
    RegisterUpdate,
)
from app.users.models import User

# Statuses after which a passed due date no longer counts as overdue.
FINISHED = {"closed", "resolved", "decided", "superseded"}
_LEVEL = {Level.LOW.value: 1, Level.MEDIUM.value: 2, Level.HIGH.value: 3}


def _invalid(field: str, issue: str, message: str) -> AppError:
    return AppError(
        422,
        "VALIDATION_ERROR",
        "The request is not valid.",
        [{"field": field, "issue": issue, "message": message}],
    )


def _not_found(kind: RegisterKind) -> AppError:
    return AppError(404, "NOT_FOUND", f"{kind.value.capitalize()} not found.")


async def _check_owner(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    member = await session.scalar(
        select(ProjectMember.id)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            User.is_active.is_(True),
        )
    )
    if member is None:
        raise _invalid("owner_id", "not_a_member", "The owner must be an active project member.")


def _check_fields(kind: RegisterKind, data: RegisterFields) -> None:
    sent = data.model_fields_set
    for other, fields in KIND_FIELDS.items():
        wrong = sorted(sent & fields) if other is not kind else []
        if wrong:
            raise _invalid(wrong[0], "not_for_kind", f"{wrong[0]} is not a field of a {kind}.")
    if data.status is not None and data.status not in {s.value for s in STATUSES[kind]}:
        allowed = ", ".join(s.value for s in STATUSES[kind])
        raise _invalid("status", "invalid", f"A {kind} status is one of: {allowed}.")


def _plain(value: Any) -> Any:
    return value.value if isinstance(value, StrEnum) else value


async def items_out(session: AsyncSession, items: list[RegisterItem]) -> list[RegisterItemOut]:
    ids = {i.owner_id for i in items if i.owner_id} | {i.created_by for i in items}
    people: dict[uuid.UUID, PersonBrief] = {}
    if ids:
        for u in await session.scalars(select(User).where(User.id.in_(ids))):
            people[u.id] = PersonBrief(id=u.id, name=u.name, email=u.email)
    today = datetime.now(UTC).date()
    return [
        RegisterItemOut(
            id=i.id,
            project_id=i.project_id,
            kind=RegisterKind(i.kind),
            code=i.code,
            title=i.title,
            description=i.description,
            status=i.status,
            owner=people.get(i.owner_id) if i.owner_id else None,
            due_date=i.due_date,
            overdue=bool(i.due_date and i.due_date < today and i.status not in FINISHED),
            probability=Level(i.probability) if i.probability else None,
            impact=Level(i.impact) if i.impact else None,
            score=(
                _LEVEL[i.probability] * _LEVEL[i.impact] if i.probability and i.impact else None
            ),
            mitigation=i.mitigation,
            priority=TaskPriority(i.priority) if i.priority else None,
            decided_on=i.decided_on,
            decided_by=i.decided_by,
            rationale=i.rationale,
            created_by=people[i.created_by],
            created_at=i.created_at,
            updated_at=i.updated_at,
            version=i.version,
        )
        for i in items
    ]


async def list_items(
    session: AsyncSession, project_id: uuid.UUID, kind: RegisterKind, status: str | None
) -> tuple[list[RegisterItem], Counter[str]]:
    rows = list(
        await session.scalars(
            select(RegisterItem)
            .where(
                RegisterItem.project_id == project_id,
                RegisterItem.kind == kind.value,
                RegisterItem.archived_at.is_(None),
            )
            .order_by(RegisterItem.created_at, RegisterItem.code)
        )
    )
    counts = Counter(r.status for r in rows)
    if status:
        rows = [r for r in rows if r.status == status]
    if kind is RegisterKind.RISK:  # highest score first
        rows.sort(
            key=lambda r: -(_LEVEL.get(r.probability or "", 0) * _LEVEL.get(r.impact or "", 0))
        )
    return rows, counts


async def get_item(
    session: AsyncSession, project_id: uuid.UUID, kind: RegisterKind, item_id: uuid.UUID
) -> RegisterItem:
    item = await session.get(RegisterItem, item_id, populate_existing=True)
    if (
        item is None
        or item.project_id != project_id
        or item.kind != kind.value
        or item.archived_at is not None
    ):
        raise _not_found(kind)
    return item


async def _next_code(session: AsyncSession, project_id: uuid.UUID, kind: RegisterKind) -> str:
    await session.execute(select(Project.id).where(Project.id == project_id).with_for_update())
    used = await session.scalar(
        select(func.count(RegisterItem.id)).where(
            RegisterItem.project_id == project_id, RegisterItem.kind == kind.value
        )
    )
    return f"{PREFIX[kind]}-{(used or 0) + 1:02d}"


async def create_item(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    kind: RegisterKind,
    data: RegisterCreate,
) -> RegisterItem:
    _check_fields(kind, data)
    if data.owner_id:
        await _check_owner(session, project_id, data.owner_id)
    values = {k: _plain(v) for k, v in data.model_dump().items()}
    values["status"] = values["status"] or str(next(iter(STATUSES[kind])))
    item = RegisterItem(
        project_id=project_id,
        kind=kind.value,
        code=await _next_code(session, project_id, kind),
        created_by=actor.id,
        **values,
    )
    session.add(item)
    await session.flush()
    record_audit(
        session,
        actor,
        f"{kind.value}.created",
        kind.value,
        item.id,
        project_id=project_id,
        after={"code": item.code, "title": item.title},
    )
    await session.commit()
    await session.refresh(item)
    return item


async def _commit(session: AsyncSession, kind: RegisterKind) -> None:
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise AppError(
            409, "VERSION_CONFLICT", f"The {kind.value} was changed by someone else. Reload."
        ) from None


async def update_item(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    kind: RegisterKind,
    item_id: uuid.UUID,
    data: RegisterUpdate,
) -> RegisterItem:
    item = await get_item(session, project_id, kind, item_id)
    if data.version != item.version:
        raise AppError(
            409, "VERSION_CONFLICT", f"The {kind.value} was changed by someone else. Reload."
        )
    _check_fields(kind, data)
    changes = data.model_dump(exclude={"version"}, exclude_unset=True)
    if changes.get("owner_id"):
        await _check_owner(session, project_id, changes["owner_id"])
    for field, value in changes.items():
        setattr(item, field, _plain(value))
    record_audit(
        session,
        actor,
        f"{kind.value}.updated",
        kind.value,
        item.id,
        project_id=project_id,
        after={"changed": sorted(changes)},
    )
    await _commit(session, kind)
    await session.refresh(item)
    return item


async def archive_item(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    kind: RegisterKind,
    item_id: uuid.UUID,
) -> None:
    item = await get_item(session, project_id, kind, item_id)
    item.archived_at = datetime.now(UTC)
    record_audit(
        session,
        actor,
        f"{kind.value}.archived",
        kind.value,
        item.id,
        project_id=project_id,
        before={"code": item.code, "title": item.title},
    )
    await _commit(session, kind)
