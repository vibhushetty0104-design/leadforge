"""Job handler contract and registry.

A handler receives a :class:`JobContext` and returns a JSON-serialisable result
dict, which is stored on the job. Raising :class:`PermanentJobError` fails the
job without retrying (bad payload, missing business, ...); any other exception
is treated as transient and retried with backoff until ``max_attempts``.

The worker only claims job types that have a registered handler, so jobs for
capabilities that are not deployed yet stay queued instead of failing. Phase 1
ships the queue machinery only; the website-audit, lead-scoring and import
handlers are registered in Phase 2 (see docs/ARCHITECTURE.md).
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from leadforge_core.models import JobType


class PermanentJobError(Exception):
    """The job can never succeed as submitted; do not retry."""


@dataclass(frozen=True)
class JobContext:
    job_id: uuid.UUID
    organization_id: uuid.UUID
    job_type: JobType
    payload: dict[str, Any]
    attempt: int
    session_factory: sessionmaker[Session]
    _stop: threading.Event = field(repr=False)

    def should_stop(self) -> bool:
        """True once shutdown was requested or the lease was lost.

        Long-running handlers should check this between steps and raise a normal
        exception to have the job re-queued for another worker.
        """
        return self._stop.is_set()


Handler = Callable[[JobContext], dict[str, Any] | None]


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[JobType, Handler] = {}

    def register(self, job_type: JobType, handler: Handler) -> None:
        if job_type in self._handlers:
            raise ValueError(f"handler already registered for {job_type.value}")
        self._handlers[job_type] = handler

    def get(self, job_type: JobType) -> Handler | None:
        return self._handlers.get(job_type)

    @property
    def job_types(self) -> list[JobType]:
        return sorted(self._handlers, key=lambda t: t.value)


def default_registry() -> HandlerRegistry:
    """Handlers shipped with this build. Empty in Phase 1 by design."""
    return HandlerRegistry()
