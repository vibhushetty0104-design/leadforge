from __future__ import annotations

from fastapi import APIRouter

from leadforge_api.deps import CurrentOrg, DbSession
from leadforge_api.schemas.dashboard import DashboardSummary
from leadforge_api.services import dashboard as service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary, summary="Organization KPIs")
def dashboard_summary(ctx: CurrentOrg, db: DbSession) -> DashboardSummary:
    return service.build_summary(db, ctx)
