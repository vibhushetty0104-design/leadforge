from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session, sessionmaker

from leadforge_core import queue
from leadforge_core.models import Job, JobStatus, JobType, Organization
from leadforge_core.models.base import utcnow
from leadforge_core.testing import is_postgres


def _enqueue(session: Session, org: Organization, **kwargs: object) -> Job:
    job = queue.enqueue(session, organization_id=org.id, job_type=JobType.WEBSITE_AUDIT, **kwargs)  # type: ignore[arg-type]
    session.commit()
    return job


def test_claim_marks_job_running_and_increments_attempts(
    session: Session, org: Organization
) -> None:
    job = _enqueue(session, org, payload={"business_id": "x"})

    claimed = queue.claim_jobs(session, worker_id="w1")
    session.commit()

    assert [j.id for j in claimed] == [job.id]
    session.refresh(job)
    assert job.status == JobStatus.RUNNING
    assert job.attempts == 1
    assert job.locked_by == "w1"
    assert job.lease_expires_at is not None
    assert queue.claim_jobs(session, worker_id="w2") == []


def test_claim_never_exceeds_limit(session: Session, org: Organization) -> None:
    for _ in range(5):
        queue.enqueue(session, organization_id=org.id, job_type=JobType.WEBSITE_AUDIT)
    session.commit()

    assert len(queue.claim_jobs(session, worker_id="w", limit=1)) == 1
    assert len(queue.claim_jobs(session, worker_id="w", limit=3)) == 3
    assert len(queue.claim_jobs(session, worker_id="w", limit=3)) == 1
    session.commit()


def test_claim_respects_priority_run_after_and_type(session: Session, org: Organization) -> None:
    low = _enqueue(session, org, priority=0)
    high = _enqueue(session, org, priority=10)
    _enqueue(session, org, priority=100, run_after=utcnow() + timedelta(hours=1))
    scoring = queue.enqueue(
        session, organization_id=org.id, job_type=JobType.LEAD_SCORING, priority=50
    )
    session.commit()

    first = queue.claim_jobs(session, worker_id="w", job_types=[JobType.WEBSITE_AUDIT])
    second = queue.claim_jobs(session, worker_id="w", job_types=[JobType.WEBSITE_AUDIT])
    third = queue.claim_jobs(session, worker_id="w", job_types=[JobType.WEBSITE_AUDIT])
    session.commit()

    assert [j.id for j in first] == [high.id]
    assert [j.id for j in second] == [low.id]
    assert third == []  # the delayed job is not yet runnable
    session.refresh(scoring)
    assert scoring.status == JobStatus.QUEUED


def test_complete_is_fenced_to_lease_holder(session: Session, org: Organization) -> None:
    job = _enqueue(session, org)
    queue.claim_jobs(session, worker_id="w1")
    session.commit()

    assert queue.complete_job(session, job.id, "intruder", {"ok": True}) is False
    assert queue.complete_job(session, job.id, "w1", {"ok": True}) is True
    session.commit()
    session.refresh(job)
    assert job.status == JobStatus.COMPLETED
    assert job.result == {"ok": True}
    assert job.locked_by is None
    assert job.finished_at is not None


def test_failure_retries_with_backoff_then_fails(session: Session, org: Organization) -> None:
    job = _enqueue(session, org, max_attempts=2)

    queue.claim_jobs(session, worker_id="w")
    assert queue.fail_job(session, job.id, "w", "boom") == JobStatus.QUEUED
    session.commit()
    session.refresh(job)
    assert job.last_error == "boom"
    assert job.run_after > utcnow() + timedelta(seconds=20)

    session.execute(update(Job).where(Job.id == job.id).values(run_after=utcnow()))
    session.commit()
    queue.claim_jobs(session, worker_id="w")
    assert queue.fail_job(session, job.id, "w", "boom again") == JobStatus.FAILED
    session.commit()
    session.refresh(job)
    assert job.attempts == 2
    assert job.status == JobStatus.FAILED
    assert job.finished_at is not None


def test_non_retryable_failure_fails_immediately(session: Session, org: Organization) -> None:
    job = _enqueue(session, org, max_attempts=5)
    queue.claim_jobs(session, worker_id="w")
    assert queue.fail_job(session, job.id, "w", "bad payload", retryable=False) == JobStatus.FAILED


def test_expired_leases_are_requeued_or_failed(session: Session, org: Organization) -> None:
    retry = _enqueue(session, org, max_attempts=3)
    exhausted = _enqueue(session, org, max_attempts=1)
    queue.claim_jobs(session, worker_id="dead-worker", limit=2)
    session.execute(update(Job).values(lease_expires_at=utcnow() - timedelta(minutes=1)))
    session.commit()

    assert queue.requeue_expired_leases(session) == 2
    session.commit()
    session.refresh(retry)
    session.refresh(exhausted)
    assert retry.status == JobStatus.QUEUED
    assert exhausted.status == JobStatus.FAILED
    assert "lease expired" in (exhausted.last_error or "")
    # The dead worker can no longer record an outcome.
    assert queue.complete_job(session, retry.id, "dead-worker") is False


def test_retry_delay_is_capped() -> None:
    assert queue.retry_delay(1) == timedelta(seconds=30)
    assert queue.retry_delay(3) == timedelta(seconds=120)
    assert queue.retry_delay(50) == timedelta(hours=1)


def test_concurrent_workers_never_claim_the_same_job(
    engine: Engine, session_factory: sessionmaker[Session], org: Organization
) -> None:
    if not is_postgres(engine):
        pytest.skip("SKIP LOCKED semantics require Postgres (set TEST_DATABASE_URL)")

    with session_factory() as s:
        for _ in range(40):
            queue.enqueue(s, organization_id=org.id, job_type=JobType.WEBSITE_AUDIT)
        s.commit()

    claimed: dict[str, list[str]] = {}
    barrier = threading.Barrier(4)

    def worker(name: str) -> None:
        mine: list[str] = []
        barrier.wait()
        while True:
            with session_factory() as s:
                jobs = queue.claim_jobs(s, worker_id=name, limit=3)
                s.commit()
            if not jobs:
                break
            mine.extend(str(j.id) for j in jobs)
        claimed[name] = mine

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    all_ids = [job_id for ids in claimed.values() for job_id in ids]
    assert len(all_ids) == 40
    assert len(set(all_ids)) == 40
