from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from leadforge_core import queue
from leadforge_core.db import build_session_factory
from leadforge_core.import_pipeline import preview_batch
from leadforge_core.models import (
    AuditLog,
    Business,
    DuplicateAction,
    ImportBatch,
    ImportRow,
    ImportRowOutcome,
    ImportStatus,
    InspectionStatus,
    Job,
    JobStatus,
    JobType,
    Organization,
    WebsiteInspection,
    WebsiteStatus,
)
from leadforge_core.models.base import utcnow
from leadforge_core.testing import make_test_engine, reset_schema, resolve_test_database_url
from leadforge_worker.handlers import DeferJob, HandlerRegistry, JobContext, default_registry
from leadforge_worker.handlers.imports import CHUNK_SIZE, handle_import
from leadforge_worker.handlers.websites import WebsiteInspector
from leadforge_worker.settings import WorkerSettings
from leadforge_worker.web.safe_fetch import FetchLimits, SafeFetcher
from leadforge_worker.worker import Worker

MAPPING = {"business_name": "name", "website": "site", "email": "email", "country": "country"}
HTML = {"content-type": "text/html"}


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
        org = Organization(name="Discovery Org", slug=f"d-{uuid.uuid4().hex[:6]}")
        s.add(org)
        s.commit()
        return org.id


def _settings(**overrides: Any) -> WorkerSettings:
    base: dict[str, Any] = {
        "database_url": resolve_test_database_url(),
        "worker_id": "test-worker",
        "lease_seconds": 30,
        "fetch_domain_interval_seconds": 0,
    }
    return WorkerSettings(**{**base, **overrides})


def _import_worker(sessions: sessionmaker[Session]) -> Worker:
    registry = HandlerRegistry()
    registry.register(JobType.IMPORT, handle_import)
    return Worker(sessions, registry, _settings())


def _batch(
    sessions: sessionmaker[Session],
    org_id: uuid.UUID,
    rows: list[dict[str, str]],
    *,
    policy: DuplicateAction = DuplicateAction.SKIP,
    resolutions: dict[int, DuplicateAction] | None = None,
    validate_websites: bool = False,
) -> uuid.UUID:
    """A confirmed import, exactly as the API leaves it."""
    with sessions() as s:
        batch = ImportBatch(
            organization_id=org_id,
            filename="t.csv",
            status=ImportStatus.QUEUED,
            headers=["name", "site", "email", "country"],
            total_rows=len(rows),
            duplicate_policy=policy,
            validate_websites=validate_websites,
        )
        s.add(batch)
        s.flush()
        for number, raw in enumerate(rows, start=2):
            s.add(
                ImportRow(
                    organization_id=org_id,
                    batch_id=batch.id,
                    row_number=number,
                    raw_data=raw,
                    resolution=(resolutions or {}).get(number),
                )
            )
        s.flush()
        preview_batch(s, batch, MAPPING)
        job = queue.enqueue(
            s,
            organization_id=org_id,
            job_type=JobType.IMPORT,
            payload={"import_id": str(batch.id)},
        )
        batch.job_id = job.id
        s.commit()
        return batch.id


def _row(name: str, site: str = "", email: str = "", country: str = "GB") -> dict[str, str]:
    return {"name": name, "site": site, "email": email, "country": country}


def _load(sessions: sessionmaker[Session], batch_id: uuid.UUID) -> ImportBatch:
    with sessions() as s:
        batch = s.get(ImportBatch, batch_id)
        assert batch is not None
        return batch


def _outcomes(sessions: sessionmaker[Session], batch_id: uuid.UUID) -> dict[int, ImportRowOutcome]:
    with sessions() as s:
        rows = s.scalars(select(ImportRow).where(ImportRow.batch_id == batch_id))
        return {row.row_number: row.outcome for row in rows}


def _businesses(sessions: sessionmaker[Session]) -> list[Business]:
    with sessions() as s:
        return list(s.scalars(select(Business).order_by(Business.name)))


def test_import_persists_valid_rows_and_records_invalid_ones(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    batch_id = _batch(
        sessions,
        org_id,
        [
            _row("Acme Dental", "acme.com", "hi@acme.com"),
            _row("No Website"),
            _row("", "nameless.com"),
            _row("Bad Site", "http://localhost/"),
        ],
    )
    assert _import_worker(sessions).run_once() is True

    batch = _load(sessions, batch_id)
    assert batch.status == ImportStatus.COMPLETED
    assert (batch.created_count, batch.invalid_count, batch.processed_rows) == (2, 2, 4)
    assert batch.finished_at is not None

    acme, no_site = _businesses(sessions)
    assert acme.domain == "acme.com"
    assert acme.website_url == "https://acme.com/"
    assert acme.website_url_original == "acme.com"
    assert acme.import_batch_id == batch_id
    assert acme.source.value == "csv_import"
    assert no_site.domain is None

    with sessions() as s:
        job = s.scalars(select(Job)).one()
        assert job.status == JobStatus.COMPLETED
        assert (job.progress_current, job.progress_total) == (4, 4)
        assert job.result is not None
        assert job.result["created"] == 2


def _existing(sessions: sessionmaker[Session], org_id: uuid.UUID, **fields: Any) -> uuid.UUID:
    with sessions() as s:
        business = Business(organization_id=org_id, **fields)
        s.add(business)
        s.commit()
        return business.id


def test_duplicates_are_skipped_by_default(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    _existing(sessions, org_id, name="Acme Dental", domain="acme.com", country_code="GB")
    batch_id = _batch(sessions, org_id, [_row("Acme Dental Ltd", "www.acme.com")])
    _import_worker(sessions).run_once()

    assert _outcomes(sessions, batch_id) == {2: ImportRowOutcome.SKIPPED_DUPLICATE}
    assert len(_businesses(sessions)) == 1
    assert _load(sessions, batch_id).skipped_count == 1


def test_update_fills_blanks_and_never_overwrites(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    business_id = _existing(
        sessions,
        org_id,
        name="Acme Dental",
        domain="acme.com",
        website_url="https://acme.com/",
        city="Leeds",
        phone="+44 1",
    )
    batch_id = _batch(
        sessions,
        org_id,
        [{**_row("Acme Dental", "acme.com", "new@acme.com"), "city": "York"}],
        policy=DuplicateAction.UPDATE,
    )
    _import_worker(sessions).run_once()

    with sessions() as s:
        business = s.get(Business, business_id)
        assert business is not None
        assert business.email == "new@acme.com"  # was blank
        assert business.city == "Leeds"  # kept
        assert business.phone == "+44 1"  # kept
        row = s.scalars(select(ImportRow)).one()
        assert row.outcome == ImportRowOutcome.UPDATED
        assert row.business_id == business_id
        assert "email" in row.warnings[-1]
        log = s.scalars(select(AuditLog)).one()
        assert log.action == "business.updated_by_import"
        assert "email" in (log.details or {})["fields"]
    assert _load(sessions, batch_id).updated_count == 1


def test_possible_duplicates_wait_for_a_person(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    _existing(sessions, org_id, name="Acme Dental", domain="acme.com")
    batch_id = _batch(
        sessions,
        org_id,
        [_row("Zenith Physio", "acme.com")],
        policy=DuplicateAction.UPDATE,
    )
    _import_worker(sessions).run_once()

    assert _outcomes(sessions, batch_id) == {2: ImportRowOutcome.NEEDS_REVIEW}
    assert [b.name for b in _businesses(sessions)] == ["Acme Dental"]
    assert _load(sessions, batch_id).review_count == 1


def test_separate_business_on_a_shared_domain(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    _existing(sessions, org_id, name="Acme Dental", domain="acme.com")
    _batch(
        sessions,
        org_id,
        [_row("Zenith Physio", "acme.com")],
        resolutions={2: DuplicateAction.CREATE},
    )
    _import_worker(sessions).run_once()

    names = [(b.name, b.domain) for b in _businesses(sessions)]
    assert names == [("Acme Dental", "acme.com"), ("Zenith Physio", "acme.com")]


def test_rows_repeated_in_a_file_create_one_record(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    batch_id = _batch(sessions, org_id, [_row("New Co", "new.com"), _row("New Co", "www.new.com/")])
    _import_worker(sessions).run_once()

    assert _outcomes(sessions, batch_id) == {
        2: ImportRowOutcome.CREATED,
        3: ImportRowOutcome.SKIPPED_DUPLICATE,
    }
    assert len(_businesses(sessions)) == 1


def test_records_added_after_preview_are_still_caught(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    batch_id = _batch(sessions, org_id, [_row("Acme Dental", "acme.com")])
    _existing(sessions, org_id, name="Acme Dental", domain="acme.com")
    _import_worker(sessions).run_once()

    assert _outcomes(sessions, batch_id) == {2: ImportRowOutcome.SKIPPED_DUPLICATE}


def test_imports_never_touch_another_organization(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    with sessions() as s:
        other = Organization(name="Other", slug="other-org")
        s.add(other)
        s.commit()
        other_id = other.id
    _existing(sessions, other_id, name="Acme Dental", domain="acme.com")
    batch_id = _batch(sessions, org_id, [_row("Acme Dental", "acme.com")])
    _import_worker(sessions).run_once()

    assert _outcomes(sessions, batch_id) == {2: ImportRowOutcome.CREATED}
    assert len(_businesses(sessions)) == 2


def test_import_can_be_interrupted_and_resumed_without_double_saving(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    rows = [_row(f"Business {i}", f"b{i}.com") for i in range(CHUNK_SIZE + 10)]
    batch_id = _batch(sessions, org_id, rows)

    worker = _import_worker(sessions)
    worker.request_stop()
    with sessions() as s:  # claim by hand: a stopping worker will not claim for itself
        job = queue.claim_jobs(s, worker_id=worker.worker_id)[0]
        s.commit()
        s.expunge(job)
    worker._process(job)

    batch = _load(sessions, batch_id)
    assert batch.status == ImportStatus.RUNNING
    assert batch.processed_rows == CHUNK_SIZE
    with sessions() as s:
        stored = s.get(Job, job.id)
        assert stored is not None
        assert stored.status == JobStatus.QUEUED
        assert stored.attempts == 0  # shutdown did not cost an attempt

    assert _import_worker(sessions).run_once() is True
    batch = _load(sessions, batch_id)
    assert batch.status == ImportStatus.COMPLETED
    assert batch.created_count == CHUNK_SIZE + 10
    assert len(_businesses(sessions)) == CHUNK_SIZE + 10


def test_final_failure_marks_the_batch_and_keeps_saved_rows(
    sessions: sessionmaker[Session], org_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch_id = _batch(sessions, org_id, [_row("Acme")])
    with sessions() as s:
        s.scalars(select(Job)).one().max_attempts = 1
        s.commit()

    def boom(*_: Any, **__: Any) -> None:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr("leadforge_worker.handlers.imports._finish", boom)
    _import_worker(sessions).run_once()

    batch = _load(sessions, batch_id)
    assert batch.status == ImportStatus.FAILED
    assert batch.error_message
    assert len(_businesses(sessions)) == 1
    with sessions() as s:
        job = s.scalars(select(Job)).one()
        assert job.status == JobStatus.FAILED
        assert "disk on fire" in (job.last_error or "")


def test_import_queues_website_validation(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    _batch(
        sessions,
        org_id,
        [_row("With Site", "acme.com"), _row("No Site")],
        validate_websites=True,
    )
    _import_worker(sessions).run_once()

    with sessions() as s:
        job = s.scalars(select(Job).where(Job.type == JobType.URL_VALIDATION)).one()
        assert job.status == JobStatus.QUEUED
        assert len(job.payload["business_ids"]) == 1


def test_a_cancelled_import_is_not_processed(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    batch_id = _batch(sessions, org_id, [_row("Acme")])
    with sessions() as s:
        batch = s.get(ImportBatch, batch_id)
        assert batch is not None
        batch.status = ImportStatus.CANCELLED
        s.commit()
    _import_worker(sessions).run_once()

    assert _businesses(sessions) == []
    with sessions() as s:
        assert s.scalars(select(Job)).one().status == JobStatus.FAILED


# --- website jobs -----------------------------------------------------------------


Respond = Callable[[httpx.Request], httpx.Response]


def _site(html: bytes = b"<title>Acme</title>", robots: bytes = b"") -> Respond:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=robots)
        return httpx.Response(200, headers=HTML, content=html)

    return respond


def _website_worker(
    sessions: sessionmaker[Session], respond: Respond, *, interval: float = 0
) -> Worker:
    inspector = WebsiteInspector(
        lambda: SafeFetcher(FetchLimits(), transport=httpx.MockTransport(respond)),
        domain_interval=interval,
    )
    registry = HandlerRegistry()
    registry.register(JobType.WEBSITE_INSPECTION, inspector.inspect)
    registry.register(JobType.URL_VALIDATION, inspector.validate_urls)
    return Worker(sessions, registry, _settings())


def _inspectable(sessions: sessionmaker[Session], org_id: uuid.UUID, **job: Any) -> uuid.UUID:
    business_id = _existing(
        sessions,
        org_id,
        name="Acme",
        domain="acme.com",
        website_url="https://acme.com/",
        notes="Precious notes",
    )
    with sessions() as s:
        queue.enqueue(
            s,
            organization_id=org_id,
            job_type=JobType.WEBSITE_INSPECTION,
            payload={"business_id": str(business_id)},
            **job,
        )
        s.commit()
    return business_id


def _inspection(sessions: sessionmaker[Session]) -> WebsiteInspection:
    with sessions() as s:
        return s.scalars(select(WebsiteInspection)).one()


def _business(sessions: sessionmaker[Session], business_id: uuid.UUID) -> Business:
    with sessions() as s:
        business = s.get(Business, business_id)
        assert business is not None
        return business


def _job(sessions: sessionmaker[Session]) -> Job:
    with sessions() as s:
        return s.scalars(select(Job)).one()


def test_inspection_saves_extracted_metadata(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    business_id = _inspectable(sessions, org_id)
    html = b'<html lang="en"><title>Acme</title><a href="mailto:hi@acme.com">x</a></html>'
    _website_worker(sessions, _site(html)).run_once()

    inspection = _inspection(sessions)
    assert inspection.status == InspectionStatus.SUCCESS
    assert inspection.title == "Acme"
    assert inspection.language == "en"
    assert inspection.emails == ["hi@acme.com"]
    assert inspection.http_status == 200
    assert inspection.fetched_at is not None

    business = _business(sessions, business_id)
    assert business.website_status == WebsiteStatus.REACHABLE
    assert business.last_inspected_at is not None
    assert business.email is None  # findings are shown, never copied silently
    assert _job(sessions).status == JobStatus.COMPLETED


def test_robots_disallow_stops_before_the_page(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    paths: list[str] = []
    site = _site(robots=b"User-agent: *\nDisallow: /\n")

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return site(request)

    business_id = _inspectable(sessions, org_id)
    _website_worker(sessions, respond).run_once()

    assert paths == ["/robots.txt"]
    assert _inspection(sessions).status == InspectionStatus.BLOCKED
    assert _inspection(sessions).error_code == "robots_disallowed"
    assert _business(sessions, business_id).website_status == WebsiteStatus.BLOCKED


@pytest.mark.parametrize(
    ("status", "website_status"),
    [
        (404, WebsiteStatus.UNREACHABLE),
        (500, WebsiteStatus.UNREACHABLE),
        (403, WebsiteStatus.BLOCKED),
    ],
)
def test_failed_websites_keep_the_business_intact(
    sessions: sessionmaker[Session],
    org_id: uuid.UUID,
    status: int,
    website_status: WebsiteStatus,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(status, headers=HTML)

    business_id = _inspectable(sessions, org_id)
    _website_worker(sessions, respond).run_once()

    inspection = _inspection(sessions)
    assert inspection.status == InspectionStatus.FAILED
    assert inspection.http_status == status
    business = _business(sessions, business_id)
    assert business.website_status == website_status
    assert business.notes == "Precious notes"
    assert business.website_url == "https://acme.com/"
    assert _job(sessions).status == JobStatus.FAILED


def test_transient_failures_retry_then_record_the_outcome(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    business_id = _inspectable(sessions, org_id, max_attempts=2)
    worker = _website_worker(sessions, respond)
    worker.run_once()

    job = _job(sessions)
    assert job.status == JobStatus.QUEUED
    assert job.attempts == 1
    with sessions() as s:
        assert s.scalars(select(WebsiteInspection)).first() is None
        stored = s.scalars(select(Job)).one()
        stored.run_after = utcnow()
        s.commit()

    worker.run_once()
    assert _job(sessions).status == JobStatus.FAILED
    inspection = _inspection(sessions)
    assert inspection.status == InspectionStatus.FAILED
    assert inspection.error_code == "timeout"
    assert _business(sessions, business_id).website_status == WebsiteStatus.UNREACHABLE


def test_oversized_pages_are_recorded_as_failures(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers=HTML, content=b"x" * (3 * 1024 * 1024))

    _inspectable(sessions, org_id)
    _website_worker(sessions, respond).run_once()
    assert _inspection(sessions).error_code == "too_large"


def test_redirect_to_a_private_address_is_blocked_end_to_end(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

    business_id = _inspectable(sessions, org_id)
    _website_worker(sessions, respond).run_once()

    inspection = _inspection(sessions)
    assert inspection.status == InspectionStatus.BLOCKED
    assert inspection.error_code == "unsafe_url"
    assert _business(sessions, business_id).website_status == WebsiteStatus.BLOCKED


def test_per_domain_throttle_defers_without_fetching(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not fetch during the throttle window")

    business_id = _inspectable(sessions, org_id)
    with sessions() as s:
        s.add(
            WebsiteInspection(
                organization_id=org_id,
                business_id=business_id,
                status=InspectionStatus.SUCCESS,
                requested_url="https://acme.com/",
                domain="acme.com",
            )
        )
        s.commit()
    _website_worker(sessions, fail, interval=60).run_once()

    job = _job(sessions)
    assert job.status == JobStatus.QUEUED
    assert job.attempts == 0
    assert job.run_after > utcnow() + timedelta(seconds=30)


def test_business_deleted_during_a_fetch_is_handled(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    business_id = _inspectable(sessions, org_id)

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            with sessions() as s:
                s.delete(s.get(Business, business_id))
                s.commit()
        return _site()(request)

    _website_worker(sessions, respond).run_once()
    with sessions() as s:
        assert s.scalars(select(WebsiteInspection)).first() is None


def test_jobs_cannot_reach_another_organizations_business(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    with sessions() as s:
        other = Organization(name="Other", slug="other-two")
        s.add(other)
        s.commit()
        other_id = other.id
    foreign_id = _existing(
        sessions, other_id, name="Foreign", domain="f.com", website_url="https://f.com/"
    )
    with sessions() as s:
        queue.enqueue(
            s,
            organization_id=org_id,
            job_type=JobType.WEBSITE_INSPECTION,
            payload={"business_id": str(foreign_id)},
        )
        s.commit()
    _website_worker(sessions, _site()).run_once()

    assert _job(sessions).status == JobStatus.FAILED
    assert _business(sessions, foreign_id).website_status == WebsiteStatus.UNKNOWN


def test_url_validation_records_reachability(
    sessions: sessionmaker[Session], org_id: uuid.UUID
) -> None:
    good = _existing(
        sessions, org_id, name="Good", domain="good.com", website_url="https://good.com/"
    )
    gone = _existing(
        sessions, org_id, name="Gone", domain="gone.com", website_url="https://gone.com/"
    )

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gone.com":
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, content=b"ok")

    with sessions() as s:
        queue.enqueue(
            s,
            organization_id=org_id,
            job_type=JobType.URL_VALIDATION,
            payload={"business_ids": [str(good), str(gone), str(uuid.uuid4())]},
        )
        s.commit()
    _website_worker(sessions, respond).run_once()

    assert _business(sessions, good).website_status == WebsiteStatus.REACHABLE
    assert _business(sessions, gone).website_status == WebsiteStatus.UNREACHABLE
    job = _job(sessions)
    assert job.status == JobStatus.COMPLETED
    assert (job.progress_current, job.progress_total) == (3, 3)


def test_default_registry_handles_every_discovery_job() -> None:
    registry = default_registry(_settings())
    assert set(registry.job_types) == {
        JobType.IMPORT,
        JobType.URL_VALIDATION,
        JobType.WEBSITE_INSPECTION,
    }


def test_should_stop_reflects_worker_shutdown() -> None:
    shutdown = threading.Event()
    context = JobContext(
        job_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        job_type=JobType.IMPORT,
        payload={},
        attempt=1,
        max_attempts=1,
        session_factory=None,  # type: ignore[arg-type]
        _stop=threading.Event(),
        _shutdown=shutdown,
        _progress=lambda current, total: None,
    )
    assert context.should_stop() is False
    shutdown.set()
    assert context.should_stop() is True


def test_defer_job_is_a_signal_not_a_failure() -> None:
    assert DeferJob(5, "later").delay_seconds == 5
