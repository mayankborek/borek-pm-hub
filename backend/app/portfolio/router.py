"""Portfolio (Manager, Account Manager) and access overview (Manager)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require
from app.common.enums import GlobalRole, ProjectStatus, RagStatus
from app.common.validation import PageParam, PageSizeParam
from app.core.database import SessionDep
from app.portfolio import service
from app.portfolio.schemas import AccessOverviewOut, PortfolioOut, PortfolioSort

router = APIRouter(tags=["portfolio"])

Search = Annotated[str | None, Query(max_length=100)]


@router.get("/portfolio", response_model=PortfolioOut)
async def portfolio(
    user: CurrentUser,
    session: SessionDep,
    q: Search = None,
    status: ProjectStatus | None = None,
    client_organisation_id: uuid.UUID | None = None,
    rag: RagStatus | None = None,
    sort: PortfolioSort = "code",
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> PortfolioOut:
    """Active projects with leads, task counts, current RAG and money: all of them for a Manager,
    those of the assigned clients for an Account Manager."""
    require(user, Action.PORTFOLIO_VIEW)
    return await service.portfolio(
        session,
        user,
        q=q,
        status=status,
        client_organisation_id=client_organisation_id,
        rag=rag,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/access-overview", response_model=AccessOverviewOut)
async def access_overview(
    user: CurrentUser,
    session: SessionDep,
    q: Search = None,
    role: GlobalRole | None = None,
    project_id: uuid.UUID | None = None,
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> AccessOverviewOut:
    """Manager: who reaches which active project, and why (membership or client assignment)."""
    require(user, Action.ACCESS_OVERVIEW)
    items, total = await service.access_overview(
        session, q=q, role=role, project_id=project_id, page=page, page_size=page_size
    )
    return AccessOverviewOut(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/access-overview/export",
    response_class=Response,
    responses={
        200: {"description": "CSV file", "content": {"text/csv": {"schema": {"type": "string"}}}}
    },
)
async def export_access_overview(
    user: CurrentUser,
    session: SessionDep,
    q: Search = None,
    role: GlobalRole | None = None,
    project_id: uuid.UUID | None = None,
) -> Response:
    """The access overview (same filters) as a CSV file."""
    require(user, Action.ACCESS_OVERVIEW)
    people, _ = await service.access_overview(
        session, q=q, role=role, project_id=project_id, page=1, page_size=None
    )
    name = f"access-overview-{datetime.now(UTC).date().isoformat()}.csv"
    return Response(
        content=service.access_csv(people),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
