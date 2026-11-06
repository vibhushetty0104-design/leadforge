from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from leadforge_api.deps import OrgContext
from leadforge_api.errors import ApiError, not_found
from leadforge_api.schemas.businesses import BulkInspectResult
from leadforge_api.schemas.imports import ImportBatchRead
from leadforge_api.schemas.inspections import BusinessInspection, DiscoverySummary, InspectionRead
from leadforge_api.schemas.jobs import JobRead
from leadforge_api.services import businesses as business_service
from leadforge_core import queue
from leadforge_core.models import (
    Business,
    ImportBatch,
    Job,
    JobStatus,
    JobType,
    WebsiteInspection,
    WebsiteStatus,
)


def _dedupe_key(business_id: uuid.UUID) -> str:
    return f"inspect:{business_id}"


def _enqueue(db: Session, ctx: OrgContext, business: Business, priority: int) -> tuple[Job, bool]:
    return queue.enqueue_unique(
        db,
        organization_id=ctx.organization_id,
        job_type=JobType.WEBSITE_INSPECTION,
        dedupe_key=_dedupe_key(business.id),
        payload={"business_id": str(business.id)},
        priority=priority,
        created_by=ctx.user_id,
    )


def request_inspection(db: Session, ctx: OrgContext, business_id: uuid.UUID) -> Job:
    business = business_service.get_business(db, ctx, business_id)
    if not business.website_url:
        raise ApiError(409, "business_has_no_website", "Add a website before inspecting it.")
    job, _ = _enqueue(db, ctx, business, priority=10)
    db.commit()
    return job


def bulk_inspect(db: Session, ctx: OrgContext, business_ids: list[uuid.UUID]) -> BulkInspectResult:
    unique_ids = list(dict.fromkeys(business_ids))
    found = business_service.get_many(db, ctx, unique_ids)
    queued = active = skipped = 0
    job_ids: list[uuid.UUID] = []
    for business in found:
        if not business.website_url:
            skipped += 1
            continue
        job, created = _enqueue(db, ctx, business, priority=0)
        job_ids.append(job.id)
        queued += created
        active += not created
    db.commit()
    return BulkInspectResult(
        queued=queued,
        already_active=active,
        skipped_no_website=skipped,
        not_found=len(unique_ids) - len(found),
        job_ids=job_ids,
    )


def latest_inspection(db: Session, ctx: OrgContext, business_id: uuid.UUID) -> BusinessInspection:
    business_service.get_business(db, ctx, business_id)
    inspection = db.scalar(
        select(WebsiteInspection)
        .where(
            WebsiteInspection.organization_id == ctx.organization_id,
            WebsiteInspection.business_id == business_id,
        )
        .order_by(WebsiteInspection.fetched_at.desc())
        .limit(1)
    )
    job = queue.find_active(db, ctx.organization_id, _dedupe_key(business_id))
    return BusinessInspection(
        inspection=InspectionRead.model_validate(inspection) if inspection else None,
        active_job=JobRead.model_validate(job) if job else None,
    )


def get_job(db: Session, ctx: OrgContext, job_id: uuid.UUID) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.organization_id == ctx.organization_id))
    if job is None:
        raise not_found("job")
    return job


def discovery_summary(db: Session, ctx: OrgContext) -> DiscoverySummary:
    org_id = ctx.organization_id

    def count(*conditions: object) -> int:
        query = select(func.count()).select_from(Business)
        query = query.where(Business.organization_id == org_id, *conditions)  # type: ignore[arg-type]
        return db.scalar(query) or 0

    statuses = dict(
        db.execute(
            select(Business.website_status, func.count())
            .where(Business.organization_id == org_id)
            .group_by(Business.website_status)
        ).all()
    )
    jobs = dict(
        db.execute(
            select(Job.status, func.count())
            .where(Job.organization_id == org_id)
            .group_by(Job.status)
        ).all()
    )
    imports = db.scalars(
        select(ImportBatch)
        .where(ImportBatch.organization_id == org_id)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
        .limit(5)
    ).all()
    by_status = {status: int(statuses.get(status, 0)) for status in WebsiteStatus}
    return DiscoverySummary(
        total_businesses=sum(by_status.values()),
        with_website=count(Business.website_url.is_not(None)),
        with_email=count(Business.email.is_not(None)),
        inspected=count(Business.last_inspected_at.is_not(None)),
        by_website_status=by_status,
        active_jobs=int(jobs.get(JobStatus.QUEUED, 0)) + int(jobs.get(JobStatus.RUNNING, 0)),
        failed_jobs=int(jobs.get(JobStatus.FAILED, 0)),
        recent_imports=[ImportBatchRead.model_validate(batch) for batch in imports],
    )
