from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from leadforge_core import queue
from leadforge_core.db import build_session_factory
from leadforge_core.models import Job, JobStatus, JobType, Organization
from leadforge_core.testing import make_test_engine, reset_schema, resolve_test_database_url
from leadforge_worker.handlers import HandlerRegistry, JobContext, PermanentJobError
from leadforge_worker.settings import WorkerSettings
from leadforge_worker.worker import Worker


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    eng = make_test_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    reset_schema(engine)
    return build_session_factory(engine)


@pytest.fixture
def org_id(sessions: sessionmaker[Session]) -> uuid.UUID:
    with sessions() as s:
        org = Organization(name="Worker Org", slug=f"w-{uuid.uuid4().hex[:6]}")
        s.add(org)
        s.commit()
        return org.id


def _settings(**overrides: Any) -> WorkerSettings:
    base: dict[str, Any] = {
        "database_url": resolve_test_database_url(),
        "worker_id": "test-worker",
        "poll_interval_seconds": 0.01,
        "max_poll_interval_seconds": 0.05,
        "lease_seconds": 30,
        "lease_recovery_interval_seconds": 0.01,
    }
    return WorkerSettings(**{**base, **overrides})


def _enqueue(sessions: sessionmaker[Session], org_id: uuid.UUID, **kwargs: Any) -> uuid.UUID:
    with sessions() as s:
        job = queue.enqueue(s, organization_id=org_id, job_type=JobType.WEBSITE_AUDIT, **kwargs)
        s.commit()
        return job.id


def _job(sessions: sessionmaker[Session], job_id: uuid.UUID) -> Job:
    with sessions() as s:
        job = s.get(Job, job_id)
        assert job is not None
        return job


def _registry(handler: Any) -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register(JobType.WEBSITE_AUDIT, handler)
    return registry


def test_successful_job_is_completed_with_result(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    seen: list[JobContext] = []

    def handler(ctx: JobContext) -> dict[str, Any]:
        seen.append(ctx)
        return {"echo": ctx.payload["value"]}

    job_id = _enqueue(sessions, org_id, payload={"value": 42})
    worker = Worker(sessions, _registry(handler), _settings())

    assert worker.run_once() is True
    assert worker.run_once() is False
    job = _job(sessions, job_id)
    assert job.status == JobStatus.COMPLETED
    assert job.result == {"echo": 42}
    assert seen[0].organization_id == org_id
    assert seen[0].attempt == 1


def test_transient_error_is_retried_and_message_recorded(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    def handler(ctx: JobContext) -> None:
        raise TimeoutError("upstream timed out")

    job_id = _enqueue(sessions, org_id, max_attempts=3)
    Worker(sessions, _registry(handler), _settings()).run_once()
    job = _job(sessions, job_id)
    assert job.status == JobStatus.QUEUED
    assert job.attempts == 1
    assert job.last_error == "TimeoutError: upstream timed out"


def test_permanent_error_fails_without_retry(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    def handler(ctx: JobContext) -> None:
        raise PermanentJobError("business no longer exists")

    job_id = _enqueue(sessions, org_id, max_attempts=5)
    Worker(sessions, _registry(handler), _settings()).run_once()
    job = _job(sessions, job_id)
    assert job.status == JobStatus.FAILED
    assert "business no longer exists" in (job.last_error or "")


def test_only_registered_job_types_are_claimed(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    with sessions() as s:
        job = queue.enqueue(s, organization_id=org_id, job_type=JobType.IMPORT)
        s.commit()
        import_id = job.id

    worker = Worker(sessions, _registry(lambda ctx: {}), _settings())
    assert worker.run_once() is False
    assert _job(sessions, import_id).status == JobStatus.QUEUED

    empty = Worker(sessions, HandlerRegistry(), _settings())
    assert empty.run_once() is False


def test_requesting_unregistered_types_is_a_config_error(sessions: sessionmaker[Session]) -> None:
    with pytest.raises(ValueError, match="no handler registered"):
        Worker(sessions, HandlerRegistry(), _settings(worker_job_types="lead_scoring"))


def test_graceful_shutdown_finishes_current_job(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    started = threading.Event()
    release = threading.Event()

    def handler(ctx: JobContext) -> dict[str, Any]:
        started.set()
        release.wait(5)
        return {"finished": True}

    first = _enqueue(sessions, org_id)
    second = _enqueue(sessions, org_id)
    worker = Worker(sessions, _registry(handler), _settings())
    thread = threading.Thread(target=worker.run_forever)
    thread.start()

    assert started.wait(5)
    worker.request_stop()  # what SIGTERM does
    release.set()
    thread.join(5)

    assert not thread.is_alive()
    statuses = {_job(sessions, first).status, _job(sessions, second).status}
    assert statuses == {JobStatus.COMPLETED, JobStatus.QUEUED}


def test_expired_leases_are_recovered_by_the_loop(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    from datetime import timedelta

    job_id = _enqueue(sessions, org_id)
    with sessions() as s:
        queue.claim_jobs(s, worker_id="crashed-worker", lease=timedelta(seconds=-1))
        s.commit()

    calls: list[uuid.UUID] = []
    worker = Worker(sessions, _registry(lambda ctx: calls.append(ctx.job_id) or {}), _settings())
    time.sleep(0.02)
    assert worker.run_once() is True
    assert calls == [job_id]
    job = _job(sessions, job_id)
    assert job.status == JobStatus.COMPLETED
    assert job.attempts == 2
