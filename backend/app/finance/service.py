"""Project money: budget and manual entries. There is no time logging and there are no rates."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.common.enums import FinanceEntryKind
from app.core.errors import AppError
from app.finance.models import FinanceEntry, ProjectBudget
from app.finance.schemas import BudgetSet, FinanceEntryCreate, FinanceOut
from app.users.models import User

_ZERO = Decimal("0.00")


def _version_conflict() -> AppError:
    return AppError(
        409, "VERSION_CONFLICT", "The budget was changed by someone else. Reload and try again."
    )


def _build(budget: ProjectBudget | None, received: Decimal, spent: Decimal) -> FinanceOut:
    amount = budget.amount if budget else None
    return FinanceOut(
        budget=amount,
        currency=budget.currency if budget else None,
        version=budget.version if budget else 0,
        received=received,
        spent=spent,
        remaining=None if amount is None else amount - spent,
        balance=received - spent,
        spent_percent=round(100 * spent / amount) if amount else None,
        over_budget=amount is not None and spent > amount,
    )


async def summaries(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, FinanceOut]:
    """One query each for budgets and sums. Projects with no budget and no entries are absent."""
    if not project_ids:
        return {}
    budgets = {
        b.project_id: b
        for b in await session.scalars(
            select(ProjectBudget).where(ProjectBudget.project_id.in_(project_ids))
        )
    }
    sums: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(dict)
    rows = await session.execute(
        select(FinanceEntry.project_id, FinanceEntry.kind, func.sum(FinanceEntry.amount))
        .where(FinanceEntry.project_id.in_(project_ids), FinanceEntry.archived_at.is_(None))
        .group_by(FinanceEntry.project_id, FinanceEntry.kind)
    )
    for project_id, kind, total in rows.all():
        sums[project_id][kind] = total
    return {
        project_id: _build(
            budgets.get(project_id),
            sums[project_id].get(FinanceEntryKind.PAYMENT.value, _ZERO),
            sums[project_id].get(FinanceEntryKind.SPEND.value, _ZERO),
        )
        for project_id in set(budgets) | set(sums)
    }


async def get_finance(session: AsyncSession, project_id: uuid.UUID) -> FinanceOut:
    found = await summaries(session, [project_id])
    return found.get(project_id) or _build(None, _ZERO, _ZERO)


async def set_budget(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: BudgetSet
) -> FinanceOut:
    budget = await session.scalar(
        select(ProjectBudget).where(ProjectBudget.project_id == project_id)
    )
    if (budget.version if budget else 0) != data.version:
        raise _version_conflict()
    if budget is not None and budget.currency != data.currency:
        entries = await session.scalar(
            select(func.count(FinanceEntry.id)).where(
                FinanceEntry.project_id == project_id, FinanceEntry.archived_at.is_(None)
            )
        )
        if entries:
            raise AppError(409, "CURRENCY_LOCKED", "The currency cannot change once entries exist.")
    before = {"amount": str(budget.amount), "currency": budget.currency} if budget else None
    if budget is None:
        budget = ProjectBudget(project_id=project_id, amount=data.amount, currency=data.currency)
        session.add(budget)
    else:
        budget.amount = data.amount
        budget.currency = data.currency
    try:
        await session.flush()
        record_audit(
            session,
            actor,
            "finance.budget_set",
            "project",
            project_id,
            project_id=project_id,
            before=before,
            after={"amount": str(data.amount), "currency": data.currency},
        )
        await session.commit()
    except (StaleDataError, IntegrityError):  # someone else set it at the same moment
        await session.rollback()
        raise _version_conflict() from None
    await session.refresh(budget)
    return await get_finance(session, project_id)


async def list_entries(
    session: AsyncSession, project_id: uuid.UUID, *, page: int, page_size: int
) -> tuple[list[FinanceEntry], int]:
    conditions = [FinanceEntry.project_id == project_id, FinanceEntry.archived_at.is_(None)]
    total = await session.scalar(select(func.count(FinanceEntry.id)).where(*conditions)) or 0
    rows = await session.scalars(
        select(FinanceEntry)
        .where(*conditions)
        .order_by(FinanceEntry.entry_date.desc(), FinanceEntry.created_at.desc(), FinanceEntry.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


async def add_entry(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: FinanceEntryCreate
) -> FinanceEntry:
    """Needs a budget first, because the budget holds the currency."""
    budget = await session.scalar(
        select(ProjectBudget.id).where(ProjectBudget.project_id == project_id)
    )
    if budget is None:
        raise AppError(409, "NO_BUDGET", "Set the project's budget first.")
    entry = FinanceEntry(
        project_id=project_id,
        kind=data.kind.value,
        amount=data.amount,
        entry_date=data.entry_date,
        description=data.description,
        created_by=actor.id,
    )
    session.add(entry)
    await session.flush()
    record_audit(
        session,
        actor,
        "finance.entry_added",
        "finance_entry",
        entry.id,
        project_id=project_id,
        after={"kind": entry.kind, "amount": str(data.amount)},
    )
    await session.commit()
    await session.refresh(entry)
    return entry


async def archive_entry(
    session: AsyncSession, actor: User, project_id: uuid.UUID, entry_id: uuid.UUID
) -> None:
    entry = await session.get(FinanceEntry, entry_id)
    if entry is None or entry.project_id != project_id or entry.archived_at is not None:
        raise AppError(404, "NOT_FOUND", "Entry not found.")
    entry.archived_at = datetime.now(UTC)
    record_audit(
        session,
        actor,
        "finance.entry_archived",
        "finance_entry",
        entry.id,
        project_id=project_id,
        before={"kind": entry.kind, "amount": str(entry.amount)},
    )
    await session.commit()
