"""Applies a confirmed CSV import in resumable chunks.

Each chunk commits on its own, so a retry or a replacement worker only picks up rows
still marked pending and a crash can never import a row twice.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leadforge_core import queue
from leadforge_core.db import session_scope
from leadforge_core.import_pipeline import (
    apply_preview,
    build_index,
    candidate_for_row,
    create_business,
    decide,
    fill_blank_fields,
    validate_rows,
)
from leadforge_core.models import (
    Business,
    ImportBatch,
    ImportRow,
    ImportRowOutcome,
    ImportStatus,
    JobType,
)
from leadforge_core.models.base import utcnow
from leadforge_worker.handlers import DeferJob, JobContext, PermanentJobError

logger = logging.getLogger("leadforge.worker.imports")

CHUNK_SIZE = 200
VALIDATION_CHUNK_SIZE = 50


def _load_batch(session: Session, ctx: JobContext) -> ImportBatch:
    try:
        batch_id = uuid.UUID(str(ctx.payload.get("import_id")))
    except ValueError as exc:
        raise PermanentJobError("Job payload has no valid import id.") from exc
    batch = session.scalar(
        select(ImportBatch).where(
            ImportBatch.id == batch_id, ImportBatch.organization_id == ctx.organization_id
        )
    )
    if batch is None:
        raise PermanentJobError("The import no longer exists.")
    return batch


def _apply_row(session: Session, batch: ImportBatch, row: ImportRow, index: Any, item: Any) -> None:
    values = item.values
    match = index.find(values["name_key"], values["domain"], values["country_code"])
    apply_preview(row, item, match)
    if not item.is_valid:
        row.processed_at = utcnow()
        return

    decision = decide(match, row.resolution, batch.duplicate_policy)
    business_id: uuid.UUID | None = None
    try:
        with session.begin_nested():
            if decision.outcome is ImportRowOutcome.CREATED:
                business_id = create_business(session, batch, values, separate=decision.separate).id
            elif decision.outcome is ImportRowOutcome.UPDATED and decision.target_id:
                changed = fill_blank_fields(session, batch, decision.target_id, values)
                if changed is None:
                    decision = decide(None, None, batch.duplicate_policy)
                    business_id = create_business(session, batch, values, separate=False).id
                else:
                    business_id = decision.target_id
                    row.warnings = [*row.warnings, _update_note(changed)]
    except IntegrityError:
        # Someone added the same domain between our duplicate check and this insert.
        row.outcome = ImportRowOutcome.SKIPPED_DUPLICATE
        row.warnings = [*row.warnings, "A matching business was added while importing."]
        row.processed_at = utcnow()
        return

    row.outcome = decision.outcome
    row.business_id = business_id or decision.target_id
    row.processed_at = utcnow()
    if decision.outcome is ImportRowOutcome.CREATED:
        index.add(candidate_for_row(row.row_number, values))


def _update_note(changed: list[str]) -> str:
    if not changed:
        return "Matched an existing business; it already had all of these details."
    return "Filled blank fields on the existing business: " + ", ".join(changed) + "."


def _refresh_counts(session: Session, batch: ImportBatch) -> int:
    """Recount from the rows so totals stay right across retries. Returns rows left."""
    counts = dict(
        session.execute(
            select(ImportRow.outcome, func.count())
            .where(ImportRow.batch_id == batch.id)
            .group_by(ImportRow.outcome)
        ).all()
    )
    pending = int(counts.get(ImportRowOutcome.PENDING, 0))
    batch.created_count = int(counts.get(ImportRowOutcome.CREATED, 0))
    batch.updated_count = int(counts.get(ImportRowOutcome.UPDATED, 0))
    batch.skipped_count = int(counts.get(ImportRowOutcome.SKIPPED_DUPLICATE, 0))
    batch.invalid_count = int(counts.get(ImportRowOutcome.INVALID, 0))
    batch.review_count = int(counts.get(ImportRowOutcome.NEEDS_REVIEW, 0))
    batch.processed_rows = batch.total_rows - pending
    return pending


def _process_chunk(ctx: JobContext) -> int:
    """Apply and commit one chunk. Returns the number of rows still pending."""
    with session_scope(ctx.session_factory) as session:
        batch = _load_batch(session, ctx)
        rows = list(
            session.scalars(
                select(ImportRow)
                .where(
                    ImportRow.batch_id == batch.id, ImportRow.outcome == ImportRowOutcome.PENDING
                )
                .order_by(ImportRow.row_number)
                .limit(CHUNK_SIZE)
            )
        )
        validated = validate_rows(rows, batch.column_mapping or {})
        index = build_index(session, batch.organization_id, validated)
        for row, item in validated:
            _apply_row(session, batch, row, index, item)
        session.flush()
        pending = _refresh_counts(session, batch)
        processed, total = batch.processed_rows, batch.total_rows
    ctx.report_progress(processed, total)
    return pending


def _finish(ctx: JobContext) -> dict[str, Any]:
    with session_scope(ctx.session_factory) as session:
        batch = _load_batch(session, ctx)
        _refresh_counts(session, batch)
        batch.warning_count = sum(
            1
            for warnings, outcome in session.execute(
                select(ImportRow.warnings, ImportRow.outcome)
                .where(ImportRow.batch_id == batch.id)
                .execution_options(yield_per=500)
            )
            if warnings and outcome is not ImportRowOutcome.INVALID
        )
        batch.status = ImportStatus.COMPLETED
        batch.finished_at = utcnow()
        checks = _enqueue_validation(session, batch) if batch.validate_websites else 0
        return {
            "created": batch.created_count,
            "updated": batch.updated_count,
            "skipped": batch.skipped_count,
            "invalid": batch.invalid_count,
            "needs_review": batch.review_count,
            "validation_jobs": checks,
        }


def _enqueue_validation(session: Session, batch: ImportBatch) -> int:
    ids = [
        str(business_id)
        for business_id in session.scalars(
            select(Business.id)
            .where(Business.import_batch_id == batch.id, Business.website_url.is_not(None))
            .order_by(Business.created_at, Business.id)
        )
    ]
    jobs = 0
    for start in range(0, len(ids), VALIDATION_CHUNK_SIZE):
        queue.enqueue_unique(
            session,
            organization_id=batch.organization_id,
            job_type=JobType.URL_VALIDATION,
            dedupe_key=f"urlcheck:{batch.id}:{jobs}",
            payload={"business_ids": ids[start : start + VALIDATION_CHUNK_SIZE]},
            created_by=batch.created_by,
        )
        jobs += 1
    return jobs


def handle_import(ctx: JobContext) -> dict[str, Any]:
    with session_scope(ctx.session_factory) as session:
        batch = _load_batch(session, ctx)
        if batch.status not in {ImportStatus.QUEUED, ImportStatus.RUNNING}:
            raise PermanentJobError(f"The import is {batch.status.value} and cannot be processed.")
        batch.status = ImportStatus.RUNNING
        batch.started_at = batch.started_at or utcnow()

    try:
        while _process_chunk(ctx) > 0:
            if ctx.should_stop():
                raise DeferJob(0, "Worker shutting down; the import will resume.")
        return _finish(ctx)
    except DeferJob:
        raise
    except Exception:
        if ctx.attempt >= ctx.max_attempts:
            logger.exception("import failed", extra={"job_id": str(ctx.job_id)})
            with session_scope(ctx.session_factory) as session:
                batch = _load_batch(session, ctx)
                batch.status = ImportStatus.FAILED
                batch.finished_at = utcnow()
                batch.error_message = "The import stopped unexpectedly. Saved rows were kept."
        raise
