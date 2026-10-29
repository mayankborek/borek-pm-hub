"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.auth.rate_limit import SlidingWindowLimiter
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from app.health.router import router as health_router


def _upload_limit_bytes() -> int:
    return get_settings().max_upload_mb * 1024 * 1024


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    # The interactive API docs are a map for attackers: off in production.
    show_docs = settings.environment != "production"

    application = FastAPI(
        title="Borek PM Hub API",
        version=__version__,
        description="Backend API for the Borek PM Hub project management platform.",
        docs_url="/docs" if show_docs else None,
        redoc_url="/redoc" if show_docs else None,
        openapi_url="/openapi.json" if show_docs else None,
    )
    application.state.login_limiter = SlidingWindowLimiter()

    # Middleware added first runs innermost. Order, outside in: request ID, security headers,
    # CORS, body size (so a 413 still gets CORS headers and the browser can read it).
    application.add_middleware(BodySizeLimitMiddleware, upload_limit=_upload_limit_bytes)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Dev-User-Id", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After", "Content-Disposition"],
    )
    application.add_middleware(
        SecurityHeadersMiddleware, hsts=settings.environment in ("staging", "production")
    )
    application.add_middleware(RequestIdMiddleware)
    register_error_handlers(application)

    application.include_router(health_router)
    application.include_router(api_router)
    return application


app = create_app()
