"""Website audits, their findings, and lead scores."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from leadforge_core.models.base import (
    Base,
    OrganizationOwnedMixin,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    str_enum,
    utcnow,
)
from leadforge_core.models.enums import AuditStatus, FindingCategory, FindingSeverity


class WebsiteAudit(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "website_audits"

    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    requested_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str | None] = mapped_column(String(2048))
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[AuditStatus] = mapped_column(
        str_enum(AuditStatus, "audit_status"),
        nullable=False,
        default=AuditStatus.QUEUED,
        server_default=AuditStatus.QUEUED.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Raw measured values (timings, page weight, detected tech). Never synthesised.
    summary: Mapped[dict[str, Any] | None] = mapped_column()
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL")
    )

    __table_args__ = (Index("ix_website_audits_org_status", "organization_id", "status"),)


class AuditFinding(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "audit_findings"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("website_audits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[FindingCategory] = mapped_column(
        str_enum(FindingCategory, "finding_category"), nullable=False
    )
    severity: Mapped[FindingSeverity] = mapped_column(
        str_enum(FindingSeverity, "finding_severity"), nullable=False
    )
    # Stable machine-readable rule identifier, e.g. "seo.missing_meta_description".
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict[str, Any] | None] = mapped_column()

    __table_args__ = (Index("ix_audit_findings_audit_severity", "audit_id", "severity"),)


class LeadScore(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    """A versioned, explainable score snapshot. History is kept; latest wins."""

    __tablename__ = "lead_scores"

    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    audit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("website_audits.id", ondelete="SET NULL"), index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    # Per-factor contributions so every score can be explained to the user.
    breakdown: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
        Index("ix_lead_scores_business_computed_at", "business_id", "computed_at"),
    )
