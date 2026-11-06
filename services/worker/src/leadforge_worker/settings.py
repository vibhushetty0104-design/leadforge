from __future__ import annotations

import os
import socket
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import NoDecode

from leadforge_core.config import CoreSettings
from leadforge_core.models import JobType


def _default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


class WorkerSettings(CoreSettings):
    worker_id: str = Field(default_factory=_default_worker_id, max_length=200)
    poll_interval_seconds: float = Field(default=2.0, gt=0, le=60)
    # Idle polling backs off up to this interval to keep free-tier databases quiet.
    max_poll_interval_seconds: float = Field(default=30.0, gt=0, le=600)
    lease_seconds: int = Field(default=300, ge=30, le=3600)
    lease_recovery_interval_seconds: float = Field(default=60.0, gt=0, le=3600)
    fetch_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    fetch_read_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    fetch_total_timeout_seconds: float = Field(default=25.0, gt=0, le=300)
    fetch_max_bytes: int = Field(default=2 * 1024 * 1024, ge=64 * 1024, le=50 * 1024 * 1024)
    fetch_max_redirects: int = Field(default=5, ge=0, le=10)
    # Minimum gap between requests to one host.
    fetch_domain_interval_seconds: float = Field(default=5.0, ge=0, le=300)
    # Optional comma-separated subset of job types this worker should process.
    worker_job_types: Annotated[list[JobType], NoDecode] = Field(default_factory=list)

    @field_validator("worker_job_types", mode="before")
    @classmethod
    def _split_types(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value
