"""Liveness (/health) and readiness (/ready, includes a database probe)."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.core.database import SessionDep
from app.core.errors import AppError

logger = logging.getLogger("app.health")

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadyResponse(BaseModel):
    status: str
    database: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness: the process is up. Does not touch the database."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/ready", response_model=ReadyResponse)
async def ready(session: SessionDep) -> ReadyResponse:
    """Readiness: the app can reach the database. A failing replica is taken out of rotation."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed")
        raise AppError(503, "DATABASE_UNAVAILABLE", "The database is not reachable.") from None
    return ReadyResponse(status="ready", database="ok")
