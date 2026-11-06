"""Website jobs: reachability checks and metadata inspection.

No database session is held during network calls, and failures are recorded next to
the business rather than on it: a dead website never damages the record.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from leadforge_core.db import session_scope
from leadforge_core.models import Business, InspectionStatus, WebsiteInspection, WebsiteStatus
from leadforge_core.models.base import utcnow
from leadforge_core.url_safety import UnsafeURLError, normalize_public_url
from leadforge_worker.handlers import DeferJob, JobContext, PermanentJobError
from leadforge_worker.web.extract import extract_page
from leadforge_worker.web.safe_fetch import FetchError, SafeFetcher

logger = logging.getLogger("leadforge.worker.websites")

_RESTRICTED_STATUSES = {401, 403, 407, 429, 451}

FetcherFactory = Callable[[], SafeFetcher]


def status_for_http(code: int) -> WebsiteStatus:
    if code < 400:
        return WebsiteStatus.REACHABLE
    return WebsiteStatus.BLOCKED if code in _RESTRICTED_STATUSES else WebsiteStatus.UNREACHABLE


def status_for_error(error: FetchError) -> WebsiteStatus:
    if error.code in {"unsafe_url", "too_many_redirects", "robots_disallowed"}:
        return WebsiteStatus.BLOCKED
    # An oversized or non-HTML response still proves something answered.
    if error.code in {"too_large", "unsupported_content"}:
        return WebsiteStatus.REACHABLE
    return WebsiteStatus.UNREACHABLE


def _get_business(session: Session, ctx: JobContext, business_id: uuid.UUID) -> Business | None:
    return session.scalar(
        select(Business).where(
            Business.id == business_id, Business.organization_id == ctx.organization_id
        )
    )


def _set_status(business: Business, status: WebsiteStatus) -> None:
    business.website_status = status
    business.website_checked_at = utcnow()


class WebsiteInspector:
    def __init__(self, fetcher_factory: FetcherFactory, domain_interval: float) -> None:
        self._fetchers = fetcher_factory
        self._interval = timedelta(seconds=domain_interval)

    def _defer_if_throttled(self, session: Session, domain: str) -> None:
        """Space out requests to a host, across every worker and organization."""
        last = session.scalar(
            select(func.max(WebsiteInspection.fetched_at)).where(WebsiteInspection.domain == domain)
        )
        if last is not None:
            wait = (last + self._interval - utcnow()).total_seconds()
            if wait > 0:
                raise DeferJob(wait, f"Waiting to respect the rate limit for {domain}.")

    def _record(
        self,
        ctx: JobContext,
        business_id: uuid.UUID,
        *,
        status: InspectionStatus,
        website_status: WebsiteStatus,
        requested_url: str,
        domain: str,
        **fields: Any,
    ) -> None:
        with session_scope(ctx.session_factory) as session:
            business = _get_business(session, ctx, business_id)
            if business is None:
                return  # deleted while the fetch ran; nothing left to attach this to
            session.add(
                WebsiteInspection(
                    organization_id=ctx.organization_id,
                    business_id=business_id,
                    job_id=ctx.job_id,
                    status=status,
                    requested_url=requested_url,
                    domain=domain,
                    **fields,
                )
            )
            _set_status(business, website_status)
            business.last_inspected_at = utcnow()

    def inspect(self, ctx: JobContext) -> dict[str, Any]:
        try:
            business_id = uuid.UUID(str(ctx.payload.get("business_id")))
        except ValueError as exc:
            raise PermanentJobError("Job payload has no valid business id.") from exc

        with session_scope(ctx.session_factory) as session:
            business = _get_business(session, ctx, business_id)
            if business is None:
                raise PermanentJobError("The business no longer exists.")
            if not business.website_url:
                raise PermanentJobError("The business has no website.")
            url = business.website_url
            try:
                domain = normalize_public_url(url).host
            except UnsafeURLError as exc:
                raise PermanentJobError(f"Refused: {exc}.") from exc
            self._defer_if_throttled(session, domain)

        def failed(error: FetchError, status: InspectionStatus) -> None:
            self._record(
                ctx,
                business_id,
                status=status,
                website_status=status_for_error(error),
                requested_url=url,
                domain=domain,
                error_code=error.code,
                error_message=error.message,
            )

        ctx.report_progress(0, 1)
        with self._fetchers() as fetcher:
            if not fetcher.allowed_by_robots(url):
                failed(
                    FetchError("robots_disallowed", "The site's robots.txt disallows this page."),
                    InspectionStatus.BLOCKED,
                )
                return {"status": InspectionStatus.BLOCKED.value, "reason": "robots_disallowed"}
            try:
                page = fetcher.fetch(url)
            except FetchError as error:
                if error.retryable and ctx.attempt < ctx.max_attempts:
                    raise
                failed(
                    error,
                    InspectionStatus.BLOCKED
                    if error.code == "unsafe_url"
                    else InspectionStatus.FAILED,
                )
                raise PermanentJobError(error.message) from error

        common: dict[str, Any] = {
            "final_url": page.final_url,
            "http_status": page.status_code,
            "redirect_count": page.redirect_count,
            "response_bytes": len(page.body),
            "fetched_at": page.fetched_at,
        }
        website_status = status_for_http(page.status_code)
        if page.status_code >= 400:
            self._record(
                ctx,
                business_id,
                status=InspectionStatus.FAILED,
                website_status=website_status,
                requested_url=url,
                domain=domain,
                error_code="http_error",
                error_message=f"The site responded with HTTP {page.status_code}.",
                **common,
            )
            raise PermanentJobError(f"The site responded with HTTP {page.status_code}.")

        data = extract_page(page.body, base_url=page.final_url, charset=page.charset)
        self._record(
            ctx,
            business_id,
            status=InspectionStatus.SUCCESS,
            website_status=website_status,
            requested_url=url,
            domain=domain,
            title=data.title,
            meta_description=data.meta_description,
            canonical_url=data.canonical_url,
            language=data.language,
            headings=data.headings,
            contact_links=data.contact_links,
            emails=data.emails,
            phones=data.phones,
            social_links=data.social_links,
            **common,
        )
        ctx.report_progress(1, 1)
        return {"status": InspectionStatus.SUCCESS.value, "http_status": page.status_code}

    def validate_urls(self, ctx: JobContext) -> dict[str, Any]:
        raw_ids = ctx.payload.get("business_ids")
        if not isinstance(raw_ids, list):
            raise PermanentJobError("Job payload has no business ids.")
        counts = {status.value: 0 for status in WebsiteStatus}
        hosts_seen: dict[str, float] = {}
        interval = self._interval.total_seconds()
        with self._fetchers() as fetcher:
            for position, raw_id in enumerate(raw_ids, start=1):
                if ctx.should_stop():
                    raise DeferJob(0, "Worker shutting down; validation will resume.")
                business_id = uuid.UUID(str(raw_id))
                with session_scope(ctx.session_factory) as session:
                    business = _get_business(session, ctx, business_id)
                    url = business.website_url if business else None
                if url is None:
                    ctx.report_progress(position, len(raw_ids))
                    continue

                host = normalize_public_url(url).host
                wait = hosts_seen.get(host, 0) + interval - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                hosts_seen[host] = time.monotonic()

                try:
                    status = status_for_http(fetcher.probe(url).status_code)
                except FetchError as error:
                    status = status_for_error(error)
                counts[status.value] += 1
                with session_scope(ctx.session_factory) as session:
                    business = _get_business(session, ctx, business_id)
                    if business is not None:
                        _set_status(business, status)
                ctx.report_progress(position, len(raw_ids))
        return counts
