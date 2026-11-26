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
    """PMs, Managers and Account Managers: metrics for active projects plus the blocked and
    overdue tasks. A PM gets their own projects, an Account Manager their clients' projects and
    those they are a member of, a Manager all of them."""
    require(user, Action.DASHBOARD_VIEW)
    return await service.pm_dashboard(session, user, limit)


@router.get("/me", response_model=MyDashboard)
async def my_dashboard(
    user: CurrentUser,
    session: SessionDep,
    limit: Limit = 10,
    focus_limit: Annotated[int, Query(ge=1, le=20, description="Tasks in My Focus")] = 4,
) -> MyDashboard:
    """My Work: my assigned-task counts (with due this week / today), My Focus, my projects
    with per-member counts, and my blocked and overdue tasks (Needs Attention)."""
    require(user, Action.MY_TASKS)
    return await service.my_dashboard(session, user, limit, focus_limit)
