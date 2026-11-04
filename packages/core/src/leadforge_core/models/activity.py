"""CRM activity timeline and the security audit log."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, Uuid, func
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
from leadforge_core.models.enums import ActivityType


class Activity(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    """Interactions and follow-ups. A follow-up has ``due_at`` and, once done, ``completed_at``."""

    __tablename__ = "activities"

    business_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="SET NULL")
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    type: Mapped[ActivityType] = mapped_column(
        str_enum(ActivityType, "activity_type"), nullable=False
    )
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL")
    )

    __table_args__ = (
        Index("ix_activities_org_occurred_at", "organization_id", "occurred_at"),
        Index("ix_activities_org_due_at", "organization_id", "due_at"),
    )


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only record of security-relevant actions.

    Deliberately has no ``updated_at`` (rows are never modified) and keeps rows
    when the organization or actor is deleted (FKs are SET NULL), so history
    survives account removal.
    """

    __tablename__ = "audit_logs"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    details: Mapped[dict[str, Any] | None] = mapped_column()
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now(), default=utcnow
    )

    __table_args__ = (Index("ix_audit_logs_org_created_at", "organization_id", "created_at"),)
