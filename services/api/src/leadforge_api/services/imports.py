"""CSV import lifecycle: upload, map and preview, resolve duplicates, confirm."""

from __future__ import annotations

import uuid
from itertools import islice
from pathlib import PurePosixPath, PureWindowsPath
from typing import BinaryIO

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from leadforge_api.deps import OrgContext
from leadforge_api.errors import ApiError, not_found
from leadforge_api.schemas.common import PageParams
from leadforge_api.schemas.imports import (
    ImportConfirmRequest,
    ImportDetail,
    ImportPreviewSummary,
)
from leadforge_api.schemas.jobs import JobRead
from leadforge_api.services import audit_log
from leadforge_core import queue
from leadforge_core.csv_import import (
    PREVIEW_ROWS,
    CsvFormatError,
    CsvRowLimitError,
    ImportField,
    parse_csv,
    suggest_mapping,
)
from leadforge_core.import_pipeline import mark_abandoned_rows, preview_batch
from leadforge_core.models import (
    DuplicateAction,
    ImportBatch,
    ImportRow,
    ImportRowOutcome,
    ImportStatus,
    Job,
    JobStatus,
    JobType,
    MemberRole,
)
from leadforge_core.models.base import utcnow

_INSERT_CHUNK = 500
_ACTIVE = (ImportStatus.QUEUED, ImportStatus.RUNNING)


def clean_filename(filename: str) -> str:
    name = PureWindowsPath(PurePosixPath(filename).name).name.strip()[:255]
    if not name.lower().endswith(".csv"):
        raise ApiError(422, "import_invalid_file", "Only .csv files can be imported.")
    return name


def ingest(
    db: Session,
    ctx: OrgContext,
    stream: BinaryIO,
    *,
    filename: str,
    size_bytes: int,
    max_rows: int,
) -> ImportBatch:
    """Parse an uploaded file into rows awaiting mapping. Holds at most one chunk in memory."""
    batch = ImportBatch(
        organization_id=ctx.organization_id,
        created_by=ctx.user_id,
        filename=filename,
        size_bytes=size_bytes,
    )
    db.add(batch)
    try:
        parsed = parse_csv(stream, max_rows=max_rows)
        batch.headers = parsed.headers
        db.flush()
        total = 0
        while chunk := list(islice(parsed.rows, _INSERT_CHUNK)):
            db.execute(
                insert(ImportRow),
                [
                    {
                        "id": uuid.uuid4(),
                        "organization_id": ctx.organization_id,
                        "batch_id": batch.id,
                        "row_number": row_number,
                        "raw_data": row,
                        "errors": [],
                        "warnings": [],
                    }
                    for row_number, row in chunk
                ],
            )
            total += len(chunk)
    except CsvRowLimitError as exc:
        db.rollback()
        raise ApiError(413, "import_too_many_rows", str(exc)) from exc
    except CsvFormatError as exc:
        db.rollback()
        raise ApiError(422, "import_invalid_csv", str(exc)) from exc

    if total == 0:
        db.rollback()
        raise ApiError(422, "import_invalid_csv", "The file has a header but no data rows.")
    batch.total_rows = total
    audit_log.record(
        db,
        organization_id=ctx.organization_id,
        actor_id=ctx.user_id,
        action="import.uploaded",
        entity_type="import_batch",
        entity_id=batch.id,
        request_id=ctx.request_id,
        details={"filename": filename, "rows": total},
    )
    db.commit()
    return batch


def get_batch(db: Session, ctx: OrgContext, import_id: uuid.UUID) -> ImportBatch:
    batch = db.scalar(
        select(ImportBatch).where(
            ImportBatch.id == import_id, ImportBatch.organization_id == ctx.organization_id
        )
    )
    if batch is None:
        raise not_found("import")
    return _reconcile(db, batch)


def _reconcile(db: Session, batch: ImportBatch) -> ImportBatch:
    """A worker that died mid-import cannot update its batch; the job records the end."""
    if batch.status in _ACTIVE and batch.job_id is not None:
        job = db.get(Job, batch.job_id)
        if job is not None and job.status == JobStatus.FAILED:
            batch.status = ImportStatus.FAILED
            batch.error_message = "The import stopped unexpectedly. Rows already saved were kept."
            batch.finished_at = utcnow()
            db.commit()
    return batch


def list_batches(db: Session, ctx: OrgContext, page: PageParams) -> tuple[list[ImportBatch], int]:
    org = ImportBatch.organization_id == ctx.organization_id
    total = db.scalar(select(func.count()).select_from(ImportBatch).where(org)) or 0
    rows = db.scalars(
        select(ImportBatch)
        .where(org)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return [_reconcile(db, batch) for batch in rows], total


def preview_summary(db: Session, batch: ImportBatch) -> ImportPreviewSummary | None:
    if batch.column_mapping is None:
        return None
    rows = db.execute(
        select(ImportRow.outcome, ImportRow.warnings, ImportRow.duplicate, ImportRow.resolution)
        .where(ImportRow.batch_id == batch.id)
        .execution_options(yield_per=500)
    )
    invalid = warnings = definite = possible = resolved = 0
    for outcome, row_warnings, duplicate, resolution in rows:
        if outcome == ImportRowOutcome.INVALID:
            invalid += 1
            continue
        warnings += bool(row_warnings)
        resolved += bool(resolution and duplicate)
        if duplicate:
            definite += duplicate["kind"] == "definite"
            possible += duplicate["kind"] == "possible"
    return ImportPreviewSummary(
        total=batch.total_rows,
        valid=batch.total_rows - invalid,
        invalid=invalid,
        with_warnings=warnings,
        definite_duplicates=definite,
        possible_duplicates=possible,
        resolved=resolved,
    )


def detail(db: Session, batch: ImportBatch) -> ImportDetail:
    sample = db.scalars(
        select(ImportRow.raw_data)
        .where(ImportRow.batch_id == batch.id)
        .order_by(ImportRow.row_number)
        .limit(PREVIEW_ROWS)
    ).all()
    job = db.get(Job, batch.job_id) if batch.job_id else None
    return ImportDetail(
        **{
            name: getattr(batch, name)
            for name in ImportDetail.model_fields
            if name not in {"suggested_mapping", "sample_rows", "preview", "job", "column_mapping"}
        },
        column_mapping=batch.column_mapping,
        suggested_mapping=suggest_mapping(batch.headers),
        sample_rows=[
            {key: value for key, value in row.items() if key != "__extra_columns__"}
            for row in sample
        ],
        preview=preview_summary(db, batch) if batch.status == ImportStatus.DRAFT else None,
        job=JobRead.model_validate(job) if job else None,
    )


def _require_draft(batch: ImportBatch) -> None:
    if batch.status != ImportStatus.DRAFT:
        raise ApiError(409, "import_not_editable", "This import has already been submitted.")


def set_mapping(
    db: Session, ctx: OrgContext, import_id: uuid.UUID, mapping: dict[ImportField, str]
) -> ImportBatch:
    batch = get_batch(db, ctx, import_id)
    _require_draft(batch)
    if not mapping.get(ImportField.BUSINESS_NAME):
        raise ApiError(422, "import_invalid_mapping", "Map a column to the business name.")
    selected = [header for header in mapping.values() if header]
    unknown = sorted(set(selected) - set(batch.headers))
    if unknown:
        raise ApiError(422, "import_invalid_mapping", f"Unknown columns: {', '.join(unknown)}.")
    if len(selected) != len(set(selected)):
        raise ApiError(422, "import_invalid_mapping", "Each column can only be mapped once.")
    preview_batch(db, batch, {field.value: header for field, header in mapping.items() if header})
    db.commit()
    return batch


def list_rows(
    db: Session,
    ctx: OrgContext,
    import_id: uuid.UUID,
    page: PageParams,
    *,
    outcome: ImportRowOutcome | None,
    duplicates_only: bool,
) -> tuple[list[ImportRow], int]:
    batch = get_batch(db, ctx, import_id)
    conditions = [ImportRow.batch_id == batch.id]
    if outcome is not None:
        conditions.append(ImportRow.outcome == outcome)
    if duplicates_only:
        conditions.append(ImportRow.has_duplicate.is_(True))
    total = db.scalar(select(func.count()).select_from(ImportRow).where(*conditions)) or 0
    rows = db.scalars(
        select(ImportRow)
        .where(*conditions)
        .order_by(ImportRow.row_number)
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return list(rows), total


def _require_update_role(ctx: OrgContext) -> None:
    ctx.require_role(MemberRole.OWNER, MemberRole.ADMIN)


def resolve_row(
    db: Session,
    ctx: OrgContext,
    import_id: uuid.UUID,
    row_id: uuid.UUID,
    resolution: DuplicateAction | None,
) -> ImportRow:
    batch = get_batch(db, ctx, import_id)
    _require_draft(batch)
    if resolution is DuplicateAction.UPDATE:
        _require_update_role(ctx)
    row = db.scalar(select(ImportRow).where(ImportRow.id == row_id, ImportRow.batch_id == batch.id))
    if row is None:
        raise not_found("import_row")
    if not row.duplicate:
        raise ApiError(409, "import_row_not_duplicate", "This row has no detected duplicate.")
    if resolution is DuplicateAction.UPDATE and not row.duplicate.get("business_id"):
        raise ApiError(
            409, "import_row_no_target", "This row duplicates another row in the same file."
        )
    row.resolution = resolution
    db.commit()
    return row


def confirm(
    db: Session, ctx: OrgContext, import_id: uuid.UUID, body: ImportConfirmRequest
) -> ImportBatch:
    batch = get_batch(db, ctx, import_id)
    _require_draft(batch)
    if batch.column_mapping is None:
        raise ApiError(409, "import_not_mapped", "Map the columns before confirming the import.")

    has_row_updates = db.scalar(
        select(func.count())
        .select_from(ImportRow)
        .where(ImportRow.batch_id == batch.id, ImportRow.resolution == DuplicateAction.UPDATE)
    )
    if body.duplicate_policy is DuplicateAction.UPDATE or has_row_updates:
        _require_update_role(ctx)

    batch.duplicate_policy = body.duplicate_policy
    batch.validate_websites = body.validate_websites
    job, _ = queue.enqueue_unique(
        db,
        organization_id=ctx.organization_id,
        job_type=JobType.IMPORT,
        dedupe_key=f"import:{batch.id}",
        payload={"import_id": str(batch.id)},
        priority=5,
        created_by=ctx.user_id,
    )
    batch.job_id = job.id
    batch.status = ImportStatus.QUEUED
    audit_log.record(
        db,
        organization_id=ctx.organization_id,
        actor_id=ctx.user_id,
        action="import.confirmed",
        entity_type="import_batch",
        entity_id=batch.id,
        request_id=ctx.request_id,
        details={"duplicate_policy": body.duplicate_policy.value},
    )
    db.commit()
    return batch


def cancel(db: Session, ctx: OrgContext, import_id: uuid.UUID) -> ImportBatch:
    batch = get_batch(db, ctx, import_id)
    _require_draft(batch)
    batch.status = ImportStatus.CANCELLED
    batch.finished_at = utcnow()
    mark_abandoned_rows(db, batch.id)
    db.commit()
    return batch
