"""Businesses (prospects) and their contacts."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, Uuid, false, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from leadforge_core.dedupe import normalize_business_name
from leadforge_core.models.base import (
    Base,
    OrganizationOwnedMixin,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    str_enum,
)
from leadforge_core.models.enums import BusinessStatus, RecordSource, WebsiteStatus


class Business(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Normalised form of the URL, plus exactly what was submitted.
    website_url: Mapped[str | None] = mapped_column(String(2048))
    website_url_original: Mapped[str | None] = mapped_column(String(2048))
    # Normalised registrable host (lowercase, no "www.") used for de-duplication.
    domain: Mapped[str | None] = mapped_column(String(253))
    # Empty for the normal one-business-per-domain case. A distinct value lets
    # genuinely separate businesses share a domain while the unique index still
    # blocks accidental duplicates, including under concurrent writes.
    domain_discriminator: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    # Normalised name used for duplicate detection; maintained from ``name``.
    name_key: Mapped[str | None] = mapped_column(String(200))
    # Shown as "Category" in the product.
    industry: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(320))
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    notes: Mapped[str | None] = mapped_column(Text)
    website_status: Mapped[WebsiteStatus] = mapped_column(
        str_enum(WebsiteStatus, "website_status"),
        nullable=False,
        default=WebsiteStatus.UNKNOWN,
        server_default=WebsiteStatus.UNKNOWN.value,
    )
    website_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_inspected_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("import_batches.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[BusinessStatus] = mapped_column(
        str_enum(BusinessStatus, "business_status"),
        nullable=False,
        default=BusinessStatus.NEW,
        server_default=BusinessStatus.NEW.value,
    )
    source: Mapped[RecordSource] = mapped_column(
        str_enum(RecordSource, "business_source"),
        nullable=False,
        default=RecordSource.MANUAL,
        server_default=RecordSource.MANUAL.value,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL")
    )

    __table_args__ = (
        Index(
            "uq_businesses_organization_id_domain",
            "organization_id",
            "domain",
            "domain_discriminator",
            unique=True,
            postgresql_where=text("domain IS NOT NULL"),
            sqlite_where=text("domain IS NOT NULL"),
        ),
        Index("ix_businesses_org_status", "organization_id", "status"),
        Index("ix_businesses_org_created_at", "organization_id", "created_at"),
        Index("ix_businesses_org_name_key", "organization_id", "name_key"),
        Index("ix_businesses_org_website_status", "organization_id", "website_status"),
    )

    @validates("name")
    def _sync_name_key(self, _key: str, value: str) -> str:
        self.name_key = normalize_business_name(value)[:200] or None
        return value


class Contact(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str | None] = mapped_column(String(200))
    role_title: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    profile_url: Mapped[str | None] = mapped_column(String(2048))
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    source: Mapped[RecordSource] = mapped_column(
        str_enum(RecordSource, "contact_source"),
        nullable=False,
        default=RecordSource.MANUAL,
        server_default=RecordSource.MANUAL.value,
    )
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_contacts_org_email", "organization_id", "email"),)
