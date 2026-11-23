"""Versioned API router. Feature routers (auth, projects, tasks)."""

from fastapi import APIRouter

from app.admin.router import roles_router as admin_roles_router
from app.admin.router import router as admin_router
from app.audit.router import router as audit_router
from app.auth.router import router as auth_router
from app.capacity.router import router as capacity_router
from app.change_requests.router import router as change_requests_router
from app.client.router import router as client_router
from app.dashboard.router import router as dashboard_router
from app.finance.router import router as finance_router
from app.manager.router import router as manager_router
from app.milestones.router import router as milestones_router
from app.notifications.router import router as notifications_router
from app.organisations.router import router as organisations_router
from app.portfolio.router import router as portfolio_router
from app.projects.router import router as projects_router
from app.reporting.router import router as reporting_router
from app.requirements.router import router as requirements_router
from app.tasks.details_router import router as details_router
from app.tasks.router import router as tasks_router
from app.users.router import me_router
from app.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(tasks_router)
api_router.include_router(details_router)
api_router.include_router(dashboard_router)
api_router.include_router(users_router)
api_router.include_router(me_router)
api_router.include_router(notifications_router)
api_router.include_router(client_router)
api_router.include_router(admin_router)
api_router.include_router(admin_roles_router)
api_router.include_router(audit_router)
api_router.include_router(organisations_router)
api_router.include_router(portfolio_router)
api_router.include_router(manager_router)
api_router.include_router(capacity_router)
api_router.include_router(reporting_router)
api_router.include_router(finance_router)
api_router.include_router(milestones_router)
api_router.include_router(change_requests_router)
api_router.include_router(requirements_router)
