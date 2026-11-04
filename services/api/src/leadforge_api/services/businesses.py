from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leadforge_api.deps import OrgContext
from leadforge_api.errors import ApiError, not_found
from leadforge_api.schemas.businesses import BusinessCreate
from leadforge_api.schemas.common import PageParams
from leadforge_api.services import audit_log
from leadforge_core.models import Business, BusinessStatus, MemberRole, RecordSource
from leadforge_core.url_safety import normalize_public_url


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_businesses(
    db: Session,
    ctx: OrgContext,
    page: PageParams,
    *,
    search: str | None = None,
    status: BusinessStatus | None = None,
) -> tuple[list[Business], int]:
    conditions = [Business.organization_id == ctx.organization_id]
    if status is not None:
        conditions.append(Business.status == status)
    if search:
        pattern = f"%{_escape_like(search.lower())}%"
        conditions.append(
            or_(
                func.lower(Business.name).like(pattern, escape="\\"),
                func.lower(func.coalesce(Business.domain, "")).like(pattern, escape="\\"),
            )
        )

    total = db.scalar(select(func.count()).select_from(Business).where(*conditions)) or 0
    rows = db.scalars(
        select(Business)
        .where(*conditions)
        .order_by(Business.created_at.desc(), Business.id.desc())
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return list(rows), total


def get_business(db: Session, ctx: OrgContext, business_id: uuid.UUID) -> Business:
    business = db.scalar(
        select(Business).where(
            Business.id == business_id, Business.organization_id == ctx.organization_id
        )
    )
    if business is None:
        raise not_found("business")
    return business


def create_business(db: Session, ctx: OrgContext, data: BusinessCreate) -> Business:
    domain = normalize_public_url(data.website_url).domain if data.website_url else None
    if domain is not None:
        existing = db.scalar(
            select(Business.id).where(
                Business.organization_id == ctx.organization_id, Business.domain == domain
            )
        )
        if existing is not None:
            raise _duplicate(domain, existing)

    business = Business(
        organization_id=ctx.organization_id,
        created_by=ctx.user_id,
        source=RecordSource.MANUAL,
        domain=domain,
        **data.model_dump(),
    )
    db.add(business)
    try:
        db.flush()
    except IntegrityError as exc:
        # Lost a race with a concurrent insert of the same domain.
        db.rollback()
        raise _duplicate(domain, None) from exc

    audit_log.record(
        db,
        organization_id=ctx.organization_id,
        actor_id=ctx.user_id,
        action="business.created",
        entity_type="business",
        entity_id=business.id,
        request_id=ctx.request_id,
        details={"name": business.name, "domain": domain},
    )
    db.commit()
    return business


def delete_business(db: Session, ctx: OrgContext, business_id: uuid.UUID) -> None:
    ctx.require_role(MemberRole.OWNER, MemberRole.ADMIN)
    business = get_business(db, ctx, business_id)
    audit_log.record(
        db,
        organization_id=ctx.organization_id,
        actor_id=ctx.user_id,
        action="business.deleted",
        entity_type="business",
        entity_id=business.id,
        request_id=ctx.request_id,
        details={"name": business.name, "domain": business.domain},
    )
    db.delete(business)
    db.commit()


def _duplicate(domain: str | None, existing_id: uuid.UUID | None) -> ApiError:
    return ApiError(
        409,
        "business_already_exists",
        f"A business with the domain {domain} already exists in this organization.",
        {"domain": domain, "existing_id": str(existing_id) if existing_id else None},
    )
