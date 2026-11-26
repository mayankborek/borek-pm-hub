"""Portfolio (Manager, Account Manager) and the person access matrix (Manager, Admin)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require
from app.common.enums import GlobalRole, ProjectStatus, RagStatus
from app.common.validation import PageParam, PageSizeParam
from app.core.database import SessionDep
from app.portfolio import service
from app.portfolio.access_pdf import build_access_pdf
from app.portfolio.schemas import AccessOverviewOut, PortfolioOut, PortfolioSort, PortfolioStage

router = APIRouter(tags=["portfolio"])

Search = Annotated[str | None, Query(max_length=100)]
ProjectIds = Annotated[
    list[uuid.UUID],
    Query(max_length=100, description="Repeat to filter by several projects (any of them)."),
]
PersonIds = Annotated[
    list[uuid.UUID],
    Query(max_length=200, description="Repeat to show only these people (multi-select)."),
]


@router.get("/portfolio", response_model=PortfolioOut)
async def portfolio(
    user: CurrentUser,
    session: SessionDep,
    q: Search = None,
    status: ProjectStatus | None = None,
    client_organisation_id: uuid.UUID | None = None,
    rag: RagStatus | None = None,
    stage: PortfolioStage | None = None,
    sort: PortfolioSort = "code",
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> PortfolioOut:
    """Active projects with leads, task counts, current RAG, published progress, next milestone
    and money: all of them for a Manager, those of the assigned clients for an Account Manager.
    `stage`: active (not completed or cancelled) or completed."""
    require(user, Action.PORTFOLIO_VIEW)
    return await service.portfolio(
        session,
        user,
        q=q,
        status=status,
        client_organisation_id=client_organisation_id,
        rag=rag,
        stage=stage,
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
    project_id: ProjectIds = [],  # noqa: B006 (FastAPI copies query defaults)
    person_id: PersonIds = [],  # noqa: B006
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> AccessOverviewOut:
    """Person access (Manager, Administrator): each person's single global role and the active
    projects they reach, and why (membership, client assignment, named client contact)."""
    require(user, Action.ACCESS_OVERVIEW)
    items, total = await service.access_overview(
        session,
        q=q,
        role=role,
        project_ids=project_id,
        person_ids=person_id,
        page=page,
        page_size=page_size,
    )
    return AccessOverviewOut(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/access-overview/export",
    response_class=Response,
    responses={
        200: {
            "description": "CSV or PDF file",
            "content": {
                "text/csv": {"schema": {"type": "string"}},
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
)
async def export_access_overview(
    user: CurrentUser,
    session: SessionDep,
    q: Search = None,
    role: GlobalRole | None = None,
    project_id: ProjectIds = [],  # noqa: B006
    person_id: PersonIds = [],  # noqa: B006
    format: Literal["csv", "pdf"] = "csv",
) -> Response:
    """The whole filtered matrix (all pages, same order and fields) as CSV or PDF."""
    require(user, Action.ACCESS_OVERVIEW)
    people, _ = await service.access_overview(
        session,
        q=q,
        role=role,
        project_ids=project_id,
        person_ids=person_id,
        page=1,
        page_size=None,
    )
    now = datetime.now(UTC)
    name = f"access-overview-{now.date().isoformat()}.{format}"
    headers = {"Content-Disposition": f'attachment; filename="{name}"'}
    if format == "pdf":
        filters = [f"search: {q.strip()}"] if q and q.strip() else []
        if role:
            filters.append(f"role: {role.value}")
        if project_id:
            filters.append(f"{len(project_id)} project(s)")
        if person_id:
            filters.append(f"{len(person_id)} selected people")
        return Response(
            content=build_access_pdf(people, filters=filters, exported_at=now),
            media_type="application/pdf",
            headers=headers,
        )
    return Response(
        content=service.access_csv(people),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )
