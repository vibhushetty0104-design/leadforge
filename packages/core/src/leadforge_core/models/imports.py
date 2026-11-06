"""CSV import batches and their per-row results."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from leadforge_core.models.base import (
    Base,
    OrganizationOwnedMixin,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    str_enum,
)
from leadforge_core.models.enums import DuplicateAction, ImportRowOutcome, ImportStatus


class ImportBatch(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "import_batches"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[ImportStatus] = mapped_column(
        str_enum(ImportStatus, "import_status"),
        nullable=False,
        default=ImportStatus.DRAFT,
        server_default=ImportStatus.DRAFT.value,
    )
    headers: Mapped[list[str]] = mapped_column(nullable=False, default=list)
    # {"business_name": "Company", "website": "URL", ...}
    column_mapping: Mapped[dict[str, Any] | None] = mapped_column()
    duplicate_policy: Mapped[DuplicateAction] = mapped_column(
        str_enum(DuplicateAction, "import_duplicate_policy"),
        nullable=False,
        default=DuplicateAction.SKIP,
        server_default=DuplicateAction.SKIP.value,
    )
    validate_websites: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    processed_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    updated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    invalid_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    warning_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (
        Index("ix_import_batches_org_created_at", "organization_id", "created_at"),
        Index("ix_import_batches_org_status", "organization_id", "status"),
    )


class ImportRow(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "import_rows"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    normalized: Mapped[dict[str, Any] | None] = mapped_column()
    errors: Mapped[list[str]] = mapped_column(nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(nullable=False, default=list)
    duplicate: Mapped[dict[str, Any] | None] = mapped_column()
    has_duplicate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    outcome: Mapped[ImportRowOutcome] = mapped_column(
        str_enum(ImportRowOutcome, "import_row_outcome"),
        nullable=False,
        default=ImportRowOutcome.PENDING,
        server_default=ImportRowOutcome.PENDING.value,
    )
    # An explicit per-row decision; overrides the batch duplicate policy.
    resolution: Mapped[DuplicateAction | None] = mapped_column(
        str_enum(DuplicateAction, "import_row_resolution")
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="SET NULL"), index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (
        UniqueConstraint("batch_id", "row_number"),
        Index("ix_import_rows_batch_outcome", "batch_id", "outcome"),
    )
