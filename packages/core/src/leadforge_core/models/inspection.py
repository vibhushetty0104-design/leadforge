"""Snapshots of public website metadata. History is kept; the latest row wins."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, SmallInteger, String, Text, Uuid
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
from leadforge_core.models.enums import InspectionStatus


class WebsiteInspection(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "website_inspections"

    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[InspectionStatus] = mapped_column(
        str_enum(InspectionStatus, "inspection_status"), nullable=False
    )
    requested_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str | None] = mapped_column(String(2048))
    # The host actually contacted; drives per-domain throttling across workers.
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    redirect_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    response_bytes: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    title: Mapped[str | None] = mapped_column(String(500))
    meta_description: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    language: Mapped[str | None] = mapped_column(String(35))
    headings: Mapped[list[dict[str, Any]]] = mapped_column(nullable=False, default=list)
    contact_links: Mapped[list[dict[str, Any]]] = mapped_column(nullable=False, default=list)
    emails: Mapped[list[str]] = mapped_column(nullable=False, default=list)
    phones: Mapped[list[str]] = mapped_column(nullable=False, default=list)
    social_links: Mapped[list[dict[str, Any]]] = mapped_column(nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_website_inspections_business_fetched", "business_id", "fetched_at"),
        Index("ix_website_inspections_domain_fetched", "domain", "fetched_at"),
    )
