from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from leadforge_api.schemas.common import ApiModel
from leadforge_core.models import JobStatus, JobType


class JobRead(ApiModel):
    id: uuid.UUID
    type: JobType
    status: JobStatus
    attempts: int
    max_attempts: int
    progress_current: int
    progress_total: int | None
    last_error: str | None = Field(description="Most recent failure, including retried ones")
    result: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
