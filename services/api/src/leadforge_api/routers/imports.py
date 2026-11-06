from __future__ import annotations

import tempfile
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from starlette.concurrency import run_in_threadpool

from leadforge_api.deps import CurrentOrg, DbSession
from leadforge_api.errors import ApiError
from leadforge_api.schemas.common import Page, PageParams, page_params
from leadforge_api.schemas.imports import (
    ImportBatchRead,
    ImportConfirmRequest,
    ImportDetail,
    ImportMappingRequest,
    ImportRowRead,
    ImportRowResolutionRequest,
)
from leadforge_api.services import imports as service
from leadforge_api.settings import ApiSettings
from leadforge_core.models import ImportRowOutcome

router = APIRouter(prefix="/imports", tags=["imports"])

SPOOL_BYTES = 1024 * 1024
ALLOWED_CONTENT_TYPES = {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"}


def _too_large(limit: int) -> ApiError:
    return ApiError(413, "import_too_large", f"CSV files may be at most {limit / 1_000_000:g} MB.")


@router.post(
    "/csv",
    response_model=ImportDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CSV as the raw request body",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def upload_csv(
    request: Request,
    ctx: CurrentOrg,
    db: DbSession,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
) -> ImportDetail:
    settings: ApiSettings = request.app.state.settings
    limit = settings.import_max_upload_bytes
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError(415, "unsupported_media_type", "Send the file as text/csv.")
    name = service.clean_filename(filename)
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise _too_large(limit)

    # Counted while streaming: a client can omit or misstate Content-Length.
    with tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES) as spool:
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                raise _too_large(limit)
            spool.write(chunk)
        spool.seek(0)
        batch = await run_in_threadpool(
            service.ingest,
            db,
            ctx,
            spool,  # type: ignore[arg-type]
            filename=name,
            size_bytes=size,
            max_rows=settings.import_max_rows,
        )
        return await run_in_threadpool(service.detail, db, batch)


@router.get("", response_model=Page[ImportBatchRead], summary="Import history (paginated)")
def list_imports(
    ctx: CurrentOrg, db: DbSession, page: Annotated[PageParams, Depends(page_params)]
) -> Page[ImportBatchRead]:
    rows, total = service.list_batches(db, ctx, page)
    return Page[ImportBatchRead](
        items=[ImportBatchRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{import_id}", response_model=ImportDetail, summary="One import, with progress")
def get_import(import_id: uuid.UUID, ctx: CurrentOrg, db: DbSession) -> ImportDetail:
    return service.detail(db, service.get_batch(db, ctx, import_id))


@router.post(
    "/{import_id}/mapping",
    response_model=ImportDetail,
    summary="Save the column mapping and validate every row against it",
)
def set_mapping(
    import_id: uuid.UUID, body: ImportMappingRequest, ctx: CurrentOrg, db: DbSession
) -> ImportDetail:
    return service.detail(db, service.set_mapping(db, ctx, import_id, body.column_mapping))


@router.get(
    "/{import_id}/results",
    response_model=Page[ImportRowRead],
    summary="Per-row validation, duplicate and outcome details",
)
def list_results(
    import_id: uuid.UUID,
    ctx: CurrentOrg,
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    outcome: ImportRowOutcome | None = None,
    duplicates_only: bool = False,
) -> Page[ImportRowRead]:
    rows, total = service.list_rows(
        db, ctx, import_id, page, outcome=outcome, duplicates_only=duplicates_only
    )
    return Page[ImportRowRead](
        items=[ImportRowRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.patch(
    "/{import_id}/rows/{row_id}",
    response_model=ImportRowRead,
    summary="Decide what happens to one duplicate row",
)
def resolve_row(
    import_id: uuid.UUID,
    row_id: uuid.UUID,
    body: ImportRowResolutionRequest,
    ctx: CurrentOrg,
    db: DbSession,
) -> ImportRowRead:
    row = service.resolve_row(db, ctx, import_id, row_id, body.resolution)
    return ImportRowRead.model_validate(row)


@router.post(
    "/{import_id}/confirm",
    response_model=ImportDetail,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue the import for background processing",
)
def confirm_import(
    import_id: uuid.UUID, body: ImportConfirmRequest, ctx: CurrentOrg, db: DbSession
) -> ImportDetail:
    return service.detail(db, service.confirm(db, ctx, import_id, body))


@router.post(
    "/{import_id}/cancel", response_model=ImportDetail, summary="Discard an unconfirmed import"
)
def cancel_import(import_id: uuid.UUID, ctx: CurrentOrg, db: DbSession) -> ImportDetail:
    return service.detail(db, service.cancel(db, ctx, import_id))
