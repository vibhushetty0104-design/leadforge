"""Application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from leadforge_api import __version__
from leadforge_api.auth import SupabaseTokenVerifier
from leadforge_api.errors import register_error_handlers
from leadforge_api.middleware import RequestContextMiddleware
from leadforge_api.routers import businesses, dashboard, health, me
from leadforge_api.schemas.common import ErrorResponse
from leadforge_api.settings import ApiSettings, get_settings
from leadforge_core.db import build_session_factory, engine_from_settings
from leadforge_core.log import configure_logging

logger = logging.getLogger("leadforge.api")

API_PREFIX = "/api/v1"
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422, 500)
}


def create_app(settings: ApiSettings | None = None, *, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    engine = engine or engine_from_settings(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("api starting", extra={"environment": settings.environment.value})
        yield
        engine.dispose()

    app = FastAPI(
        title="LEADFORGE API",
        version=__version__,
        description="Prospect intelligence and website auditing platform.",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.token_verifier = SupabaseTokenVerifier(settings)

    register_error_handlers(app)
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_credentials=False,  # bearer tokens, not cookies
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Organization-Id", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
            max_age=600,
        )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    for router in (me.router, dashboard.router, businesses.router):
        app.include_router(router, prefix=API_PREFIX, responses=ERROR_RESPONSES)
    return app
