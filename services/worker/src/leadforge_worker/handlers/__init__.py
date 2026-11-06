"""Job handler contract and registry.

A handler receives a :class:`JobContext` and returns a JSON-serialisable result
dict, which is stored on the job. Raising :class:`PermanentJobError` fails the
job without retrying (bad payload, missing business, ...); any other exception
is treated as transient and retried with backoff until ``max_attempts``.

The worker only claims job types that have a registered handler, so jobs for
capabilities that are not deployed yet stay queued instead of failing. Raising
:class:`DeferJob` puts a job back in the queue without spending an attempt.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session, sessionmaker

from leadforge_core.models import JobType

if TYPE_CHECKING:
    from leadforge_worker.settings import WorkerSettings


class PermanentJobError(Exception):
    """The job can never succeed as submitted; do not retry."""


class DeferJob(Exception):  # noqa: N818 - a control signal, not an error
    """Run this job again later. Does not count as a failed attempt."""

    def __init__(self, delay_seconds: float, reason: str) -> None:
        super().__init__(reason)
        self.delay_seconds = delay_seconds
        self.reason = reason


@dataclass(frozen=True)
class JobContext:
    job_id: uuid.UUID
    organization_id: uuid.UUID
    job_type: JobType
    payload: dict[str, Any]
    attempt: int
    max_attempts: int
    session_factory: sessionmaker[Session]
    _stop: threading.Event = field(repr=False)
    _shutdown: threading.Event = field(repr=False)
    _progress: Callable[[int, int | None], None] = field(repr=False)

    def should_stop(self) -> bool:
        """True once shutdown was requested or the lease was lost.

        Long-running handlers should check this between steps and raise a normal
        exception to have the job re-queued for another worker.
        """
        return self._stop.is_set() or self._shutdown.is_set()

    def report_progress(self, current: int, total: int | None = None) -> None:
        self._progress(current, total)


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


def default_registry(settings: WorkerSettings) -> HandlerRegistry:
    """Handlers shipped with this build. Audits and scoring arrive in a later phase."""
    from leadforge_worker.handlers.imports import handle_import
    from leadforge_worker.handlers.websites import WebsiteInspector
    from leadforge_worker.web.safe_fetch import FetchLimits, SafeFetcher

    limits = FetchLimits(
        connect_timeout=settings.fetch_connect_timeout_seconds,
        read_timeout=settings.fetch_read_timeout_seconds,
        total_timeout=settings.fetch_total_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
        max_redirects=settings.fetch_max_redirects,
    )
    inspector = WebsiteInspector(
        lambda: SafeFetcher(limits), domain_interval=settings.fetch_domain_interval_seconds
    )
    registry = HandlerRegistry()
    registry.register(JobType.IMPORT, handle_import)
    registry.register(JobType.WEBSITE_INSPECTION, inspector.inspect)
    registry.register(JobType.URL_VALIDATION, inspector.validate_urls)
    return registry
