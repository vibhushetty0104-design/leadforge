from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from leadforge_api.deps import CurrentOrg, DbSession
from leadforge_api.schemas.businesses import BusinessCreate, BusinessRead
from leadforge_api.schemas.common import Page, PageParams, page_params
from leadforge_api.services import businesses as service
from leadforge_core.models import BusinessStatus

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.get("", response_model=Page[BusinessRead], summary="List businesses (paginated)")
def list_businesses(
    ctx: CurrentOrg,
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    q: Annotated[
        str | None, Query(min_length=1, max_length=100, description="Name or domain contains")
    ] = None,
    status_filter: Annotated[BusinessStatus | None, Query(alias="status")] = None,
) -> Page[BusinessRead]:
    rows, total = service.list_businesses(db, ctx, page, search=q, status=status_filter)
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


@router.get("/{business_id}", response_model=BusinessRead, summary="Get one business")
def get_business(business_id: uuid.UUID, ctx: CurrentOrg, db: DbSession) -> BusinessRead:
    return BusinessRead.model_validate(service.get_business(db, ctx, business_id))


@router.delete(
    "/{business_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a business and its dependent records (owner/admin)",
)
def delete_business(business_id: uuid.UUID, ctx: CurrentOrg, db: DbSession) -> Response:
    service.delete_business(db, ctx, business_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
