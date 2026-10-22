"""Versioned API router. Feature routers (auth, projects, tasks)."""

from fastapi import APIRouter

from app.auth.router import router as auth_router
from app.dashboard.router import router as dashboard_router
from app.projects.router import router as projects_router
from app.tasks.details_router import router as details_router
from app.tasks.router import router as tasks_router
from app.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(tasks_router)
api_router.include_router(details_router)
api_router.include_router(dashboard_router)
api_router.include_router(users_router)
