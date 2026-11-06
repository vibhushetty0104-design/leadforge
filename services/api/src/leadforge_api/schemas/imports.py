from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from leadforge_api.schemas.common import ApiModel, InputModel
from leadforge_api.schemas.jobs import JobRead
from leadforge_core.csv_import import ImportField
from leadforge_core.models import DuplicateAction, ImportRowOutcome, ImportStatus


class ImportBatchRead(ApiModel):
    id: uuid.UUID
    filename: str
    size_bytes: int
    status: ImportStatus
    total_rows: int
    processed_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    invalid_count: int
    review_count: int
    warning_count: int
    duplicate_policy: DuplicateAction
    validate_websites: bool
    error_message: str | None
    job_id: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ImportPreviewSummary(BaseModel):
    total: int
    valid: int
    invalid: int
    with_warnings: int
    definite_duplicates: int
    possible_duplicates: int
    resolved: int


class ImportDetail(ImportBatchRead):
    headers: list[str]
    column_mapping: dict[ImportField, str] | None
    suggested_mapping: dict[ImportField, str]
    sample_rows: list[dict[str, str]]
    preview: ImportPreviewSummary | None
    job: JobRead | None


class ImportMappingRequest(InputModel):
    column_mapping: dict[ImportField, str]


class ImportRowRead(ApiModel):
    id: uuid.UUID
    row_number: int
    raw_data: dict[str, Any]
    normalized: dict[str, Any] | None
    errors: list[str]
    warnings: list[str]
    duplicate: dict[str, Any] | None
    outcome: ImportRowOutcome
    resolution: DuplicateAction | None
    business_id: uuid.UUID | None


class ImportRowResolutionRequest(InputModel):
    resolution: DuplicateAction | None


class ImportConfirmRequest(InputModel):
    duplicate_policy: DuplicateAction = DuplicateAction.SKIP
    validate_websites: bool = True
