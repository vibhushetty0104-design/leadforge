from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from leadforge_api.schemas.businesses import BusinessSummary
from leadforge_core.models import BusinessStatus, JobStatus


class OrganizationBrief(BaseModel):
    id: uuid.UUID
    name: str
    is_development_seed: bool


class BusinessStats(BaseModel):
    total: int
    added_last_30_days: int
    by_status: dict[BusinessStatus, int]


class AuditStats(BaseModel):
    total: int
    completed: int
    failed: int
    in_progress: int


class ScoreStats(BaseModel):
    scored_businesses: int
    average_latest_score: float | None


class OutreachStats(BaseModel):
    active_campaigns: int
    drafts_awaiting_review: int
    suppressions: int


class FollowUpStats(BaseModel):
    open: int
    overdue: int


class DashboardSummary(BaseModel):
    organization: OrganizationBrief
    businesses: BusinessStats
    audits: AuditStats
    scores: ScoreStats
    outreach: OutreachStats
    follow_ups: FollowUpStats
    jobs: dict[JobStatus, int]
    recent_businesses: list[BusinessSummary]
    generated_at: datetime
