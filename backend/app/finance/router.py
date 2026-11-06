"""Project money: Manager, and the Account Manager of the project's client. Nobody else, so there is
no separate read rule and no money field in any other project response."""

import uuid

from fastapi import APIRouter

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action
from app.common.validation import PageParam, PageSizeParam
from app.core.database import SessionDep
from app.finance import service
from app.finance.schemas import (
    BudgetSet,
    FinanceEntryCreate,
    FinanceEntryListOut,
    FinanceEntryOut,
    FinanceOut,
)
from app.projects.service import authorize

router = APIRouter(prefix="/projects/{project_id}/finance", tags=["finance"])


@router.get("", response_model=FinanceOut)
async def get_finance(project_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> FinanceOut:
    """Budget, received, spent and remaining."""
    await authorize(session, user, project_id, Action.FINANCE_MANAGE)
    return await service.get_finance(session, project_id)


@router.put("/budget", response_model=FinanceOut)
async def set_budget(
    project_id: uuid.UUID, body: BudgetSet, user: CurrentUser, session: SessionDep
) -> FinanceOut:
    await authorize(session, user, project_id, Action.FINANCE_MANAGE, writable=True)
    return await service.set_budget(session, user, project_id, body)


@router.get("/entries", response_model=FinanceEntryListOut)
async def list_entries(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> FinanceEntryListOut:
    await authorize(session, user, project_id, Action.FINANCE_MANAGE)
    entries, total = await service.list_entries(session, project_id, page=page, page_size=page_size)
    return FinanceEntryListOut(
        items=[FinanceEntryOut.model_validate(e, from_attributes=True) for e in entries],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/entries", response_model=FinanceEntryOut, status_code=201)
async def add_entry(
    project_id: uuid.UUID, body: FinanceEntryCreate, user: CurrentUser, session: SessionDep
) -> FinanceEntryOut:
    """A client payment or money spent, entered by hand."""
    await authorize(session, user, project_id, Action.FINANCE_MANAGE, writable=True)
    entry = await service.add_entry(session, user, project_id, body)
    return FinanceEntryOut.model_validate(entry, from_attributes=True)


@router.delete("/entries/{entry_id}", status_code=204)
async def archive_entry(
    project_id: uuid.UUID, entry_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """A wrong entry is archived and no longer counted. Nothing is deleted."""
    await authorize(session, user, project_id, Action.FINANCE_MANAGE, writable=True)
    await service.archive_entry(session, user, project_id, entry_id)
