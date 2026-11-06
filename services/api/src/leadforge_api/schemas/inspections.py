from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from leadforge_api.schemas.common import ApiModel
from leadforge_api.schemas.imports import ImportBatchRead
from leadforge_api.schemas.jobs import JobRead
from leadforge_core.models import InspectionStatus, WebsiteStatus


class InspectionRead(ApiModel):
    id: uuid.UUID
    business_id: uuid.UUID
    status: InspectionStatus
    requested_url: str
    final_url: str | None
    http_status: int | None
    redirect_count: int
    response_bytes: int | None
    fetched_at: datetime
    title: str | None
    meta_description: str | None
    canonical_url: str | None
    language: str | None
    headings: list[dict[str, Any]]
    contact_links: list[dict[str, Any]]
    emails: list[str]
    phones: list[str]
    social_links: list[dict[str, Any]]
    error_code: str | None
    error_message: str | None


class BusinessInspection(BaseModel):
    inspection: InspectionRead | None
    active_job: JobRead | None


class DiscoverySummary(BaseModel):
    total_businesses: int
    with_website: int
    with_email: int
    inspected: int
    by_website_status: dict[WebsiteStatus, int]
    active_jobs: int
    failed_jobs: int
    recent_imports: list[ImportBatchRead]
