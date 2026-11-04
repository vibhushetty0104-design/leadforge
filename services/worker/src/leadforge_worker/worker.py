"""Polling worker: claim → run handler with lease heartbeat → record outcome."""

from __future__ import annotations

import logging
import signal
import threading
import time
from datetime import timedelta
from types import FrameType

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from leadforge_core import queue
from leadforge_core.db import session_scope
from leadforge_core.log import correlation_id
from leadforge_core.models import Job, JobType
from leadforge_worker.handlers import HandlerRegistry, JobContext, PermanentJobError
from leadforge_worker.settings import WorkerSettings

logger = logging.getLogger("leadforge.worker")


class Worker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        registry: HandlerRegistry,
        settings: WorkerSettings,
        stop_event: threading.Event | None = None,
    ) -> None:
        self._sessions = session_factory
        self._registry = registry
        self._settings = settings
        self._stop = stop_event or threading.Event()
        self._lease = timedelta(seconds=settings.lease_seconds)
        self._last_recovery = 0.0

        requested = settings.worker_job_types or registry.job_types
        missing = [t.value for t in requested if registry.get(t) is None]
        if missing:
            raise ValueError(f"no handler registered for requested job types: {missing}")
        self._job_types: list[JobType] = list(requested)

    @property
    def worker_id(self) -> str:
        return self._settings.worker_id

    def request_stop(self) -> None:
        self._stop.set()

    def install_signal_handlers(self) -> None:
        def _handle(signum: int, _frame: FrameType | None) -> None:
            logger.info("shutdown requested; finishing current job", extra={"signal": signum})
            self.request_stop()

        signal.signal(signal.SIGINT, _handle)
        signal.signal(signal.SIGTERM, _handle)

    # -- main loop -----------------------------------------------------------------

    def run_forever(self) -> None:
        logger.info(
            "worker started",
            extra={"worker_id": self.worker_id, "job_types": [t.value for t in self._job_types]},
        )
        if not self._job_types:
            logger.warning(
                "no job handlers are registered in this build; the worker will only "
                "recover expired leases until handlers are added"
            )
        idle = self._settings.poll_interval_seconds
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except SQLAlchemyError:
                logger.exception("database error in worker loop; backing off")
                worked = False
            if worked:
                idle = self._settings.poll_interval_seconds
                continue
            self._stop.wait(idle)
            idle = min(idle * 2, self._settings.max_poll_interval_seconds)
        logger.info("worker stopped", extra={"worker_id": self.worker_id})

    def run_once(self) -> bool:
        """Process at most one job. Returns True if a job was processed."""
        self._maybe_recover_leases()
        if not self._job_types or self._stop.is_set():
            return False

        with session_scope(self._sessions) as session:
            jobs = queue.claim_jobs(
                session,
                worker_id=self.worker_id,
                limit=1,
                job_types=self._job_types,
                lease=self._lease,
            )
            if not jobs:
                return False
            job = jobs[0]
            session.expunge(job)

        self._process(job)
        return True

    # -- internals -----------------------------------------------------------------

    def _maybe_recover_leases(self) -> None:
        now = time.monotonic()
        if now - self._last_recovery < self._settings.lease_recovery_interval_seconds:
            return
        self._last_recovery = now
        with session_scope(self._sessions) as session:
            recovered = queue.requeue_expired_leases(session)
        if recovered:
            logger.warning("recovered jobs with expired leases", extra={"count": recovered})

    def _process(self, job: Job) -> None:
        handler = self._registry.get(job.type)
        token = correlation_id.set(f"job:{job.id}")
        job_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat, args=(job, job_stop), name=f"lease-{job.id}", daemon=True
        )
        started = time.perf_counter()
        log_extra = {"job_id": str(job.id), "job_type": job.type.value, "attempt": job.attempts}
        logger.info("job started", extra=log_extra)
        heartbeat.start()
        try:
            if handler is None:  # defensive: only registered types are claimed
                raise PermanentJobError(f"no handler registered for {job.type.value}")
            context = JobContext(
                job_id=job.id,
                organization_id=job.organization_id,
                job_type=job.type,
                payload=dict(job.payload or {}),
                attempt=job.attempts,
                session_factory=self._sessions,
                _stop=job_stop,
            )
            result = handler(context)
        except PermanentJobError as exc:
            logger.error("job failed permanently", extra={**log_extra, "error": str(exc)})
            self._record_failure(job, exc, retryable=False)
        except Exception as exc:
            logger.exception("job raised; will retry if attempts remain", extra=log_extra)
            self._record_failure(job, exc, retryable=True)
        else:
            with session_scope(self._sessions) as session:
                if not queue.complete_job(session, job.id, self.worker_id, result):
                    logger.warning(
                        "lease lost before completion; result discarded", extra=log_extra
                    )
            duration = round((time.perf_counter() - started) * 1000, 1)
            logger.info("job completed", extra={**log_extra, "duration_ms": duration})
        finally:
            job_stop.set()
            heartbeat.join(timeout=5)
            correlation_id.reset(token)

    def _record_failure(self, job: Job, exc: BaseException, *, retryable: bool) -> None:
        message = f"{type(exc).__name__}: {exc}"
        with session_scope(self._sessions) as session:
            status = queue.fail_job(session, job.id, self.worker_id, message, retryable=retryable)
        if status is None:
            logger.warning(
                "lease lost before failure could be recorded", extra={"job_id": str(job.id)}
            )

    def _heartbeat(self, job: Job, job_stop: threading.Event) -> None:
        interval = max(self._settings.lease_seconds / 3, 1.0)
        while not job_stop.wait(interval):
            if self._stop.is_set():
                # Let the handler know shutdown was requested; it may finish or bail out.
                job_stop.set()
                return
            try:
                with session_scope(self._sessions) as session:
                    held = queue.extend_lease(session, job.id, self.worker_id, self._lease)
            except SQLAlchemyError:
                logger.exception("failed to extend lease", extra={"job_id": str(job.id)})
                continue
            if not held:
                logger.error(
                    "lease lost; signalling handler to stop", extra={"job_id": str(job.id)}
                )
                job_stop.set()
                return
