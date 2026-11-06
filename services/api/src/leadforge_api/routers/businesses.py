from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from leadforge_api.deps import CurrentOrg, DbSession
from leadforge_api.schemas.businesses import (
    BulkInspectRequest,
    BulkInspectResult,
    BusinessCreate,
    BusinessExportRequest,
    BusinessFilters,
    BusinessRead,
    BusinessUpdate,
)
from leadforge_api.schemas.common import Page, PageParams, page_params
from leadforge_api.schemas.inspections import BusinessInspection
from leadforge_api.schemas.jobs import JobRead
from leadforge_api.services import businesses as service
from leadforge_api.services import exports, inspections

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.get("", response_model=Page[BusinessRead], summary="List businesses (paginated)")
def list_businesses(
    ctx: CurrentOrg,
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    filters: Annotated[BusinessFilters, Query()],
) -> Page[BusinessRead]:
    rows, total = service.list_businesses(db, ctx, page, filters)
    return Page[BusinessRead](
        items=[BusinessRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "",
    response_model=BusinessRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a business manually",
)
def create_business(body: BusinessCreate, ctx: CurrentOrg, db: DbSession) -> BusinessRead:
    return BusinessRead.model_validate(service.create_business(db, ctx, body))


@router.post(
    "/export",
    summary="Export businesses as CSV (filters or explicit ids)",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_businesses(
    body: BusinessExportRequest, ctx: CurrentOrg, db: DbSession, background: BackgroundTasks
) -> StreamingResponse:
    output = exports.export_businesses(db, ctx, body)
    background.add_task(output.close)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return StreamingResponse(
        iter(lambda: output.read(64 * 1024), b""),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="leadforge-businesses-{stamp}.csv"'},
        background=background,
    )


@router.post(
    "/bulk-inspect",
    response_model=BulkInspectResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue website inspections for up to 100 businesses",
)
def bulk_inspect(body: BulkInspectRequest, ctx: CurrentOrg, db: DbSession) -> BulkInspectResult:
    return inspections.bulk_inspect(db, ctx, body.business_ids)


@router.get("/{business_id}", response_model=BusinessRead, summary="Get one business")
def get_business(business_id: uuid.UUID, ctx: CurrentOrg, db: DbSession) -> BusinessRead:
    return BusinessRead.model_validate(service.get_business(db, ctx, business_id))


@router.patch("/{business_id}", response_model=BusinessRead, summary="Update a business")
def update_business(
    business_id: uuid.UUID, body: BusinessUpdate, ctx: CurrentOrg, db: DbSession
) -> BusinessRead:
    return BusinessRead.model_validate(service.update_business(db, ctx, business_id, body))


@router.delete(
    "/{business_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a business and its dependent records (owner/admin)",
)
def delete_business(business_id: uuid.UUID, ctx: CurrentOrg, db: DbSession) -> Response:
    service.delete_business(db, ctx, business_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{business_id}/inspect",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a website inspection (returns the active job if one exists)",
)
def inspect_business(business_id: uuid.UUID, ctx: CurrentOrg, db: DbSession) -> JobRead:
    return JobRead.model_validate(inspections.request_inspection(db, ctx, business_id))


@router.get(
    "/{business_id}/inspection",
    response_model=BusinessInspection,
    summary="Latest website inspection and any active job",
)
def get_inspection(business_id: uuid.UUID, ctx: CurrentOrg, db: DbSession) -> BusinessInspection:
    return inspections.latest_inspection(db, ctx, business_id)
