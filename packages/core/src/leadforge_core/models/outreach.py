"""Campaigns, human-reviewed email drafts and suppression lists."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from leadforge_core.models.base import (
    Base,
    OrganizationOwnedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum,
)
from leadforge_core.models.enums import CampaignStatus, EmailDraftStatus, SuppressionReason


class Campaign(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CampaignStatus] = mapped_column(
        str_enum(CampaignStatus, "campaign_status"),
        nullable=False,
        default=CampaignStatus.DRAFT,
        server_default=CampaignStatus.DRAFT.value,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL")
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name"),
        Index("ix_campaigns_org_status", "organization_id", "status"),
    )


class EmailDraft(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "email_drafts"

    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EmailDraftStatus] = mapped_column(
        str_enum(EmailDraftStatus, "email_draft_status"),
        nullable=False,
        default=EmailDraftStatus.DRAFT,
        server_default=EmailDraftStatus.DRAFT.value,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL")
    )

    __table_args__ = (Index("ix_email_drafts_org_status", "organization_id", "status"),)


class Suppression(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    """Addresses or whole domains that must never be contacted."""

    __tablename__ = "suppressions"

    email: Mapped[str | None] = mapped_column(String(320))
    domain: Mapped[str | None] = mapped_column(String(253))
    reason: Mapped[SuppressionReason] = mapped_column(
        str_enum(SuppressionReason, "suppression_reason"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR domain IS NOT NULL", name="email_or_domain"),
        Index(
            "uq_suppressions_organization_id_email",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
            sqlite_where=text("email IS NOT NULL"),
        ),
        Index(
            "uq_suppressions_organization_id_domain",
            "organization_id",
            "domain",
            unique=True,
            postgresql_where=text("domain IS NOT NULL"),
            sqlite_where=text("domain IS NOT NULL"),
        ),
    )
