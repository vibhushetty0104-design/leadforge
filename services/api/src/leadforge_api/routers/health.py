from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from leadforge_api import __version__

router = APIRouter(tags=["health"])
logger = logging.getLogger("leadforge.api.health")


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["ok", "unavailable"]


@router.get("/health", response_model=HealthResponse, summary="Liveness and database check")
def health(request: Request, response: Response) -> HealthResponse:
    database: Literal["ok", "unavailable"] = "ok"
    try:
        with request.app.state.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("database health check failed")
        database = "unavailable"

    if database != "ok":
        response.status_code = 503
    return HealthResponse(
        status="ok" if database == "ok" else "degraded", version=__version__, database=database
    )
