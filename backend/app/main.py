"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.core.config import get_settings
from app.health.router import router as health_router


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="Borek PM Hub API",
        version=__version__,
        description="Backend API for the Borek PM Hub project management platform.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health_router)
    application.include_router(api_router)
    return application


app = create_app()
