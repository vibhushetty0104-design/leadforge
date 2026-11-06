"""Postgres-backed job queue.

Claiming uses ``SELECT ... FOR UPDATE SKIP LOCKED`` inside the same statement as
the status change, so concurrent workers never receive the same job. Each claim
grants a time-limited lease; a worker that dies mid-job loses the lease and the
job is re-queued by :func:`requeue_expired_leases`. Completion and failure are
fenced on ``locked_by`` so a worker whose lease was revoked cannot overwrite the
outcome recorded by the worker that took over.

SQLite (used only by unit tests) ignores ``FOR UPDATE``; concurrency guarantees
are exercised against real Postgres in CI.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leadforge_core.models import Job, JobStatus, JobType
from leadforge_core.models.base import utcnow

MAX_ERROR_LENGTH = 4000
DEFAULT_LEASE = timedelta(minutes=5)


def _now(session: Session) -> datetime | ColumnElement[datetime]:
    """Database time on Postgres (one clock for every worker), app time elsewhere."""
    if session.get_bind().dialect.name == "postgresql":
        return func.now()
    return utcnow()


def retry_delay(
    attempt: int, *, base_seconds: float = 30.0, cap_seconds: float = 3600.0
) -> timedelta:
    """Exponential backoff: 30s, 60s, 120s ... capped at one hour."""
    return timedelta(seconds=min(cap_seconds, base_seconds * (2 ** max(attempt - 1, 0))))


def enqueue(
    session: Session,
    *,
    organization_id: uuid.UUID,
    job_type: JobType,
    payload: dict[str, Any] | None = None,
    priority: int = 0,
    max_attempts: int = 3,
    run_after: datetime | None = None,
    created_by: uuid.UUID | None = None,
    dedupe_key: str | None = None,
) -> Job:
    job = Job(
        organization_id=organization_id,
        type=job_type,
        payload=payload or {},
        priority=priority,
        max_attempts=max_attempts,
        run_after=run_after or utcnow(),
        created_by=created_by,
        dedupe_key=dedupe_key,
    )
    session.add(job)
    session.flush()
    return job


def find_active(session: Session, organization_id: uuid.UUID, dedupe_key: str) -> Job | None:
    return session.scalar(
        select(Job).where(
            Job.organization_id == organization_id,
            Job.dedupe_key == dedupe_key,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )


def enqueue_unique(
    session: Session,
    *,
    organization_id: uuid.UUID,
    job_type: JobType,
    dedupe_key: str,
    **kwargs: Any,
) -> tuple[Job, bool]:
    """Enqueue unless an equivalent job is active. Returns ``(job, created)``.

    The partial unique index settles races between concurrent requests.
    """
    existing = find_active(session, organization_id, dedupe_key)
    if existing is not None:
        return existing, False
    try:
        with session.begin_nested():
            job = enqueue(
                session,
                organization_id=organization_id,
                job_type=job_type,
                dedupe_key=dedupe_key,
                **kwargs,
            )
    except IntegrityError:
        existing = find_active(session, organization_id, dedupe_key)
        if existing is None:
            raise
        return existing, False
    return job, True


def claim_jobs(
    session: Session,
    *,
    worker_id: str,
    limit: int = 1,
    job_types: Sequence[JobType] | None = None,
    lease: timedelta = DEFAULT_LEASE,
) -> list[Job]:
    """Atomically claim up to ``limit`` runnable jobs. Caller commits."""
    now = _now(session)
    candidates = (
        select(Job.id)
        .where(Job.status == JobStatus.QUEUED, Job.run_after <= now)
        .order_by(Job.priority.desc(), Job.run_after.asc(), Job.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    if job_types:
        candidates = candidates.where(Job.type.in_(list(job_types)))

    # The candidate set must be computed exactly once. With a plain
    # ``WHERE id IN (SELECT ... LIMIT n FOR UPDATE SKIP LOCKED)`` Postgres may
    # re-evaluate the sub-select during the update and claim more than ``n``
    # rows. A MATERIALIZED CTE joined via UPDATE ... FROM pins the selection.
    picked = candidates.cte("picked_jobs")
    if session.get_bind().dialect.name == "postgresql":
        picked = picked.prefix_with("MATERIALIZED")

    stmt = (
        update(Job)
        .where(Job.id == picked.c.id, Job.status == JobStatus.QUEUED)
        .values(
            status=JobStatus.RUNNING,
            locked_by=worker_id,
            locked_at=now,
            lease_expires_at=now + lease,
            started_at=now,
            attempts=Job.attempts + 1,
            updated_at=now,
        )
        .returning(Job)
        # Refresh any instance already in the identity map with the claimed state.
        .execution_options(synchronize_session=False, populate_existing=True)
    )
    return list(session.execute(stmt).scalars().all())


def _fenced(job_id: uuid.UUID, worker_id: str) -> ColumnElement[bool]:
    return and_(Job.id == job_id, Job.status == JobStatus.RUNNING, Job.locked_by == worker_id)


def extend_lease(
    session: Session, job_id: uuid.UUID, worker_id: str, lease: timedelta = DEFAULT_LEASE
) -> bool:
    now = _now(session)
    result = session.execute(
        update(Job)
        .where(_fenced(job_id, worker_id))
        .values(lease_expires_at=now + lease, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


def update_progress(
    session: Session, job_id: uuid.UUID, worker_id: str, current: int, total: int | None = None
) -> bool:
    values: dict[str, Any] = {"progress_current": current, "updated_at": _now(session)}
    if total is not None:
        values["progress_total"] = total
    result = session.execute(
        update(Job)
        .where(_fenced(job_id, worker_id))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


def defer_job(
    session: Session, job_id: uuid.UUID, worker_id: str, delay: timedelta, reason: str
) -> bool:
    """Put a running job back in the queue without spending an attempt.

    For work that could not start or finish through no fault of its own: a
    per-domain throttle window, or a worker shutting down mid-job.
    """
    now = _now(session)
    result = session.execute(
        update(Job)
        .where(_fenced(job_id, worker_id))
        .values(
            status=JobStatus.QUEUED,
            run_after=now + delay,
            attempts=Job.attempts - 1,
            locked_by=None,
            locked_at=None,
            lease_expires_at=None,
            last_error=reason[:MAX_ERROR_LENGTH],
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


def complete_job(
    session: Session, job_id: uuid.UUID, worker_id: str, result: dict[str, Any] | None = None
) -> bool:
    """Mark a job completed. Returns False if this worker no longer holds it."""
    now = _now(session)
    outcome = session.execute(
        update(Job)
        .where(_fenced(job_id, worker_id))
        .values(
            status=JobStatus.COMPLETED,
            result=result,
            finished_at=now,
            locked_by=None,
            locked_at=None,
            lease_expires_at=None,
            last_error=None,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return bool(outcome.rowcount)  # type: ignore[attr-defined]


def fail_job(
    session: Session,
    job_id: uuid.UUID,
    worker_id: str,
    error: str,
    *,
    retryable: bool = True,
) -> JobStatus | None:
    """Record a failure; re-queue with backoff while attempts remain.

    Returns the job's new status, or None if this worker no longer holds it.
    """
    job = session.execute(
        select(Job)
        .where(_fenced(job_id, worker_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if job is None:
        return None

    now = utcnow()
    job.last_error = error[:MAX_ERROR_LENGTH]
    job.locked_by = None
    job.locked_at = None
    job.lease_expires_at = None
    if retryable and job.attempts < job.max_attempts:
        job.status = JobStatus.QUEUED
        job.run_after = now + retry_delay(job.attempts)
    else:
        job.status = JobStatus.FAILED
        job.finished_at = now
    session.flush()
    return job.status


def requeue_expired_leases(session: Session) -> int:
    """Recover jobs whose worker vanished. Returns the number of jobs touched."""
    now = _now(session)
    expired = and_(Job.status == JobStatus.RUNNING, Job.lease_expires_at < now)
    lease_error = "Worker lease expired before the job finished."
    released = {
        "locked_by": None,
        "locked_at": None,
        "lease_expires_at": None,
        "last_error": lease_error,
        "updated_at": now,
    }

    requeued = session.execute(
        update(Job)
        .where(expired, Job.attempts < Job.max_attempts)
        .values(status=JobStatus.QUEUED, run_after=now, **released)
        .execution_options(synchronize_session=False)
    )
    exhausted = session.execute(
        update(Job)
        .where(expired, Job.attempts >= Job.max_attempts)
        .values(status=JobStatus.FAILED, finished_at=now, **released)
        .execution_options(synchronize_session=False)
    )
    return int(requeued.rowcount) + int(exhausted.rowcount)  # type: ignore[attr-defined]
