"""Dashboard aggregates computed from live organization data only."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from leadforge_api.deps import OrgContext
from leadforge_api.errors import not_found
from leadforge_api.schemas.businesses import BusinessSummary
from leadforge_api.schemas.dashboard import (
    AuditStats,
    BusinessStats,
    DashboardSummary,
    FollowUpStats,
    OrganizationBrief,
    OutreachStats,
    ScoreStats,
)
from leadforge_core.models import (
    Activity,
    AuditStatus,
    Business,
    BusinessStatus,
    Campaign,
    CampaignStatus,
    EmailDraft,
    EmailDraftStatus,
    Job,
    JobStatus,
    LeadScore,
    Organization,
    Suppression,
    WebsiteAudit,
)
from leadforge_core.models.base import utcnow

RECENT_LIMIT = 5


def _count(db: Session, model: type, *conditions: object) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0  # type: ignore[arg-type]


def build_summary(db: Session, ctx: OrgContext) -> DashboardSummary:
    org_id = ctx.organization_id
    org = db.get(Organization, org_id)
    if org is None:
        raise not_found("organization")
    now = utcnow()

    status_counts = dict(
        db.execute(
            select(Business.status, func.count())
            .where(Business.organization_id == org_id)
            .group_by(Business.status)
        ).all()
    )
    by_status = {status: int(status_counts.get(status, 0)) for status in BusinessStatus}

    audit_counts = dict(
        db.execute(
            select(WebsiteAudit.status, func.count())
            .where(WebsiteAudit.organization_id == org_id)
            .group_by(WebsiteAudit.status)
        ).all()
    )

    # Average of each business's most recent score.
    latest = (
        select(LeadScore.business_id, func.max(LeadScore.computed_at).label("latest_at"))
        .where(LeadScore.organization_id == org_id)
        .group_by(LeadScore.business_id)
        .subquery()
    )
    scored, average = db.execute(
        select(func.count(LeadScore.id), func.avg(LeadScore.score)).join(
            latest,
            (LeadScore.business_id == latest.c.business_id)
            & (LeadScore.computed_at == latest.c.latest_at),
        )
    ).one()

    job_counts = dict(
        db.execute(
            select(Job.status, func.count())
            .where(Job.organization_id == org_id)
            .group_by(Job.status)
        ).all()
    )

    open_follow_up = (
        Activity.organization_id == org_id,
        Activity.due_at.is_not(None),
        Activity.completed_at.is_(None),
    )

    recent = db.scalars(
        select(Business)
        .where(Business.organization_id == org_id)
        .order_by(Business.created_at.desc(), Business.id.desc())
        .limit(RECENT_LIMIT)
    ).all()

    return DashboardSummary(
        organization=OrganizationBrief(
            id=org.id, name=org.name, is_development_seed=org.is_development_seed
        ),
        businesses=BusinessStats(
            total=sum(by_status.values()),
            added_last_30_days=_count(
                db,
                Business,
                Business.organization_id == org_id,
                Business.created_at >= now - timedelta(days=30),
            ),
            by_status=by_status,
        ),
        audits=AuditStats(
            total=sum(int(v) for v in audit_counts.values()),
            completed=int(audit_counts.get(AuditStatus.COMPLETED, 0)),
            failed=int(audit_counts.get(AuditStatus.FAILED, 0)),
            in_progress=int(audit_counts.get(AuditStatus.QUEUED, 0))
            + int(audit_counts.get(AuditStatus.RUNNING, 0)),
        ),
        scores=ScoreStats(
            scored_businesses=int(scored or 0),
            average_latest_score=round(float(average), 1) if average is not None else None,
        ),
        outreach=OutreachStats(
            active_campaigns=_count(
                db,
                Campaign,
                Campaign.organization_id == org_id,
                Campaign.status == CampaignStatus.ACTIVE,
            ),
            drafts_awaiting_review=_count(
                db,
                EmailDraft,
                EmailDraft.organization_id == org_id,
                EmailDraft.status == EmailDraftStatus.DRAFT,
            ),
            suppressions=_count(db, Suppression, Suppression.organization_id == org_id),
        ),
        follow_ups=FollowUpStats(
            open=_count(db, Activity, *open_follow_up),
            overdue=_count(db, Activity, *open_follow_up, Activity.due_at < now),
        ),
        jobs={status: int(job_counts.get(status, 0)) for status in JobStatus},
        recent_businesses=[BusinessSummary.model_validate(b) for b in recent],
        generated_at=now,
    )
