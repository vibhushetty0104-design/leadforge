from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from leadforge_api.schemas.common import ApiModel, InputModel
from leadforge_core.csv_import import normalize_email
from leadforge_core.models import BusinessStatus, RecordSource, WebsiteStatus
from leadforge_core.url_safety import UnsafeURLError, normalize_public_url

OptionalShortText = Annotated[str, StringConstraints(max_length=120)] | None
OptionalUrl = Annotated[str, StringConstraints(max_length=2048)] | None
OptionalLongText = Annotated[str, StringConstraints(max_length=5000)] | None
MAX_BULK_IDS = 100


class _BusinessFields(InputModel):
    website_url: OptionalUrl = None
    industry: OptionalShortText = Field(default=None, description="Shown as Category in the UI")
    city: OptionalShortText = None
    region: OptionalShortText = None
    country_code: Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{2}$")] | None = Field(
        default=None, description="ISO 3166-1 alpha-2"
    )
    phone: Annotated[str, StringConstraints(pattern=r"^[0-9+().\- ]{5,40}$")] | None = None
    email: Annotated[str, StringConstraints(max_length=320)] | None = None
    description: OptionalLongText = None
    source_url: OptionalUrl = None
    notes: OptionalLongText = None

    @field_validator(
        "website_url",
        "industry",
        "city",
        "region",
        "phone",
        "email",
        "description",
        "source_url",
        "notes",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("website_url", "source_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        """Checks safety only; the service stores both submitted and normalised forms."""
        if value is None:
            return None
        try:
            normalize_public_url(value)
        except UnsafeURLError as exc:
            raise ValueError(str(exc)) from exc
        return value

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_email(value)
        if normalized is None:
            raise ValueError("enter a valid email address")
        return normalized

    @field_validator("country_code")
    @classmethod
    def _upper_country(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class BusinessCreate(_BusinessFields):
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    status: BusinessStatus = BusinessStatus.NEW
    allow_duplicate: bool = Field(
        default=False, description="Keep as a separate business despite a detected duplicate"
    )


class BusinessUpdate(_BusinessFields):
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    status: BusinessStatus | None = None
    allow_duplicate: bool = False

    @field_validator("name", "status")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("this field cannot be cleared")
        return value


class BusinessRead(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    website_url: str | None
    website_url_original: str | None
    domain: str | None
    industry: str | None
    city: str | None
    region: str | None
    country_code: str | None
    phone: str | None
    email: str | None
    description: str | None
    source_url: str | None
    notes: str | None
    status: BusinessStatus
    source: RecordSource
    website_status: WebsiteStatus
    website_checked_at: datetime | None
    last_inspected_at: datetime | None
    import_batch_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class BusinessSummary(ApiModel):
    id: uuid.UUID
    name: str
    domain: str | None
    status: BusinessStatus
    created_at: datetime


class BusinessFilters(BaseModel):
    q: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    status: BusinessStatus | None = None
    industry: Annotated[str, StringConstraints(max_length=120)] | None = None
    country_code: Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{2}$")] | None = None
    source: RecordSource | None = None
    website_status: WebsiteStatus | None = None
    has_email: bool | None = None
    has_website: bool | None = None
    import_id: uuid.UUID | None = None


class BusinessExportRequest(BusinessFilters):
    """Export the given ids, or everything matching the filters when none are given."""

    business_ids: Annotated[list[uuid.UUID], Field(max_length=10_000)] | None = None


class BulkInspectRequest(InputModel):
    business_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=MAX_BULK_IDS)]


class BulkInspectResult(BaseModel):
    queued: int
    already_active: int
    skipped_no_website: int
    not_found: int
    job_ids: list[uuid.UUID]
