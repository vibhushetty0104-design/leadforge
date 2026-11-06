from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leadforge_api.deps import OrgContext
from leadforge_api.errors import ApiError, not_found
from leadforge_api.schemas.businesses import BusinessCreate, BusinessFilters, BusinessUpdate
from leadforge_api.schemas.common import PageParams
from leadforge_api.services import audit_log
from leadforge_core.dedupe import (
    DuplicateMatch,
    domain_discriminator,
    normalize_business_name,
    separate_entity_discriminator,
)
from leadforge_core.import_pipeline import find_business_duplicate
from leadforge_core.models import Business, MemberRole, RecordSource, WebsiteStatus
from leadforge_core.url_safety import NormalizedURL, normalize_public_url


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def filter_conditions(ctx: OrgContext, filters: BusinessFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Business.organization_id == ctx.organization_id]
    if filters.status is not None:
        conditions.append(Business.status == filters.status)
    if filters.source is not None:
        conditions.append(Business.source == filters.source)
    if filters.website_status is not None:
        conditions.append(Business.website_status == filters.website_status)
    if filters.country_code:
        conditions.append(Business.country_code == filters.country_code.upper())
    if filters.import_id is not None:
        conditions.append(Business.import_batch_id == filters.import_id)
    if filters.industry:
        pattern = f"%{_escape_like(filters.industry.lower())}%"
        conditions.append(func.lower(Business.industry).like(pattern, escape="\\"))
    if filters.has_email is not None:
        has_email = Business.email.is_not(None)
        conditions.append(has_email if filters.has_email else Business.email.is_(None))
    if filters.has_website is not None:
        has_site = Business.website_url.is_not(None)
        conditions.append(has_site if filters.has_website else Business.website_url.is_(None))
    if filters.q:
        pattern = f"%{_escape_like(filters.q.lower())}%"
        conditions.append(
            or_(
                func.lower(Business.name).like(pattern, escape="\\"),
                func.lower(func.coalesce(Business.domain, "")).like(pattern, escape="\\"),
            )
        )
    return conditions


def list_businesses(
    db: Session, ctx: OrgContext, page: PageParams, filters: BusinessFilters
) -> tuple[list[Business], int]:
    conditions = filter_conditions(ctx, filters)
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


def _duplicate_error(match: DuplicateMatch) -> ApiError:
    subject = f"the domain {match.domain}" if match.domain else f"the name {match.name}"
    return ApiError(
        409,
        "business_already_exists",
        f"A business with {subject} already exists in this organization.",
        {
            "kind": match.kind.value,
            "reason": match.reason,
            "name": match.name,
            "domain": match.domain,
            "existing_id": match.business_id,
        },
    )


def _race_error(domain: str | None) -> ApiError:
    # Lost a race with a concurrent insert of the same domain.
    return ApiError(
        409,
        "business_already_exists",
        f"A business with the domain {domain} already exists in this organization.",
        {"domain": domain, "existing_id": None},
    )


def _normalized(url: str | None) -> NormalizedURL | None:
    return normalize_public_url(url) if url else None


def create_business(db: Session, ctx: OrgContext, data: BusinessCreate) -> Business:
    website = _normalized(data.website_url)
    source = _normalized(data.source_url)
    domain = website.domain if website else None
    match = find_business_duplicate(
        db,
        ctx.organization_id,
        name_key=normalize_business_name(data.name)[:200] or None,
        domain=domain,
        country_code=data.country_code,
    )
    if match is not None and not data.allow_duplicate:
        raise _duplicate_error(match)

    values = data.model_dump(exclude={"allow_duplicate", "website_url", "source_url"})
    business = Business(
        organization_id=ctx.organization_id,
        created_by=ctx.user_id,
        source=RecordSource.MANUAL,
        website_url=website.url if website else None,
        website_url_original=website.original if website else None,
        domain=domain,
        domain_discriminator=(
            separate_entity_discriminator()
            if match is not None and domain
            else domain_discriminator(domain, website.url if website else None)
        ),
        source_url=source.url if source else None,
        **values,
    )
    db.add(business)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _race_error(domain) from exc

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


def update_business(
    db: Session, ctx: OrgContext, business_id: uuid.UUID, data: BusinessUpdate
) -> Business:
    business = get_business(db, ctx, business_id)
    changes: dict[str, Any] = data.model_dump(exclude_unset=True, exclude={"allow_duplicate"})

    if "website_url" in changes:
        website = _normalized(changes["website_url"])
        domain = website.domain if website else None
        if website is None or website.url != business.website_url:
            changes["website_url"] = website.url if website else None
            changes["website_url_original"] = website.original if website else None
            changes["domain"] = domain
            changes["website_status"] = WebsiteStatus.UNKNOWN
            changes["website_checked_at"] = None
            changes["domain_discriminator"] = domain_discriminator(
                domain, website.url if website else None
            )
        else:
            del changes["website_url"]
    if changes.get("source_url"):
        changes["source_url"] = normalize_public_url(changes["source_url"]).url

    identity_changed = bool({"name", "domain", "country_code"} & changes.keys())
    if identity_changed:
        name = changes.get("name", business.name)
        domain = changes.get("domain", business.domain)
        match = find_business_duplicate(
            db,
            ctx.organization_id,
            name_key=normalize_business_name(name)[:200] or None,
            domain=domain,
            country_code=changes.get("country_code", business.country_code),
            exclude_id=business.id,
        )
        if match is not None:
            if not data.allow_duplicate:
                raise _duplicate_error(match)
            if domain and "domain" in changes:
                changes["domain_discriminator"] = separate_entity_discriminator()

    for key, value in changes.items():
        setattr(business, key, value)
    audit_log.record(
        db,
        organization_id=ctx.organization_id,
        actor_id=ctx.user_id,
        action="business.updated",
        entity_type="business",
        entity_id=business.id,
        request_id=ctx.request_id,
        details={"fields": sorted(changes)},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _race_error(changes.get("domain")) from exc
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


def get_many(db: Session, ctx: OrgContext, ids: Sequence[uuid.UUID]) -> list[Business]:
    return list(
        db.scalars(
            select(Business).where(
                Business.organization_id == ctx.organization_id, Business.id.in_(list(ids))
            )
        )
    )
