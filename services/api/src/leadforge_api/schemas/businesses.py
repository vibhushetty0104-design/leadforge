from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints, field_validator

from leadforge_api.schemas.common import ApiModel, InputModel
from leadforge_core.models import BusinessStatus, RecordSource
from leadforge_core.url_safety import UnsafeURLError, normalize_public_url

OptionalShortText = Annotated[str, StringConstraints(max_length=120)] | None


class BusinessCreate(InputModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    website_url: Annotated[str, StringConstraints(max_length=2048)] | None = None
    industry: OptionalShortText = None
    city: OptionalShortText = None
    region: OptionalShortText = None
    country_code: Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{2}$")] | None = Field(
        default=None, description="ISO 3166-1 alpha-2"
    )
    phone: Annotated[str, StringConstraints(pattern=r"^[0-9+().\- ]{5,40}$")] | None = None
    notes: Annotated[str, StringConstraints(max_length=5000)] | None = None
    status: BusinessStatus = BusinessStatus.NEW

    @field_validator("website_url", "industry", "city", "region", "phone", "notes", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("website_url")
    @classmethod
    def _validate_website(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return normalize_public_url(value).url
        except UnsafeURLError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("country_code")
    @classmethod
    def _upper_country(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class BusinessRead(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    website_url: str | None
    domain: str | None
    industry: str | None
    city: str | None
    region: str | None
    country_code: str | None
    phone: str | None
    notes: str | None
    status: BusinessStatus
    source: RecordSource
    created_at: datetime
    updated_at: datetime


class BusinessSummary(ApiModel):
    id: uuid.UUID
    name: str
    domain: str | None
    status: BusinessStatus
    created_at: datetime
