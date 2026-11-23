"""Delivery overviews: the Manager dashboard and one project's delivery summary.

Dashboard: Managers (every project) and Account Managers (their clients' projects), like
/portfolio. Project overview: everyone who can see the project.
"""

import uuid

from fastapi import APIRouter

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require
from app.core.database import SessionDep
from app.manager import service
from app.manager.schemas import ManagerDashboardOut, ProjectOverviewOut
from app.projects.service import authorize

router = APIRouter(tags=["manager"])


@router.get("/manager/dashboard", response_model=ManagerDashboardOut)
async def dashboard(user: CurrentUser, session: SessionDep) -> ManagerDashboardOut:
    """KPIs, open milestones due in the next 14 days and recent delivery updates across the
    projects you oversee. Project cards come from GET /portfolio."""
    require(user, Action.PORTFOLIO_VIEW)
    return await service.dashboard(session, user)


@router.get("/projects/{project_id}/overview", response_model=ProjectOverviewOut)
async def project_overview(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ProjectOverviewOut:
    """Published progress (and its trend), milestone completion, days left, client actions, next
    milestone and recent activity."""
    project = await authorize(session, user, project_id, Action.PROJECT_VIEW)
    return await service.project_overview(session, project)
