from __future__ import annotations

import uuid

from fastapi import APIRouter

from leadforge_api.deps import CurrentOrg, DbSession
from leadforge_api.schemas.inspections import DiscoverySummary
from leadforge_api.schemas.jobs import JobRead
from leadforge_api.services import inspections as service

router = APIRouter(tags=["discovery"])


@router.get("/jobs/{job_id}", response_model=JobRead, summary="Background job status and progress")
def get_job(job_id: uuid.UUID, ctx: CurrentOrg, db: DbSession) -> JobRead:
    return JobRead.model_validate(service.get_job(db, ctx, job_id))


@router.get(
    "/discovery/summary", response_model=DiscoverySummary, summary="Discovery workspace metrics"
)
def discovery_summary(ctx: CurrentOrg, db: DbSession) -> DiscoverySummary:
    return service.discovery_summary(db, ctx)
