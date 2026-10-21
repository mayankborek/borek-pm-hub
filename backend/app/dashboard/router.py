"""Dashboard endpoints (F06 PM dashboard, F07 developer landing data)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require
from app.core.database import SessionDep
from app.dashboard import service
from app.dashboard.schemas import MyDashboard, PmDashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

Limit = Annotated[int, Query(ge=1, le=50, description="Tasks per attention list")]


@router.get("", response_model=PmDashboard)
async def pm_dashboard(user: CurrentUser, session: SessionDep, limit: Limit = 10) -> PmDashboard:
    """PM only: metrics for every active project plus the blocked and overdue tasks."""
    require(user, Action.DASHBOARD_VIEW)
    return await service.pm_dashboard(session, limit)


@router.get("/me", response_model=MyDashboard)
async def my_dashboard(user: CurrentUser, session: SessionDep, limit: Limit = 10) -> MyDashboard:
    """My assigned-task counts, my projects with per-member counts, my attention lists."""
    require(user, Action.MY_TASKS)
    return await service.my_dashboard(session, user, limit)
