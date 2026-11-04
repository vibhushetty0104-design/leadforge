from __future__ import annotations

import re
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from leadforge_api.errors import ApiError
from leadforge_api.schemas.organizations import OrganizationCreate
from leadforge_api.services import audit_log
from leadforge_core.models import MemberRole, Organization, OrganizationMember, Profile

MAX_OWNED_ORGANIZATIONS = 10


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
    return f"{base}-{secrets.token_hex(3)}"


def list_memberships(db: Session, profile: Profile) -> list[OrganizationMember]:
    return list(
        db.scalars(
            select(OrganizationMember)
            .where(OrganizationMember.profile_id == profile.id)
            .options(selectinload(OrganizationMember.organization))
            .order_by(OrganizationMember.created_at.asc())
        ).all()
    )


def create_organization(
    db: Session, profile: Profile, data: OrganizationCreate, request_id: str | None
) -> OrganizationMember:
    owned = db.scalar(
        select(func.count())
        .select_from(OrganizationMember)
        .where(
            OrganizationMember.profile_id == profile.id,
            OrganizationMember.role == MemberRole.OWNER,
        )
    )
    if (owned or 0) >= MAX_OWNED_ORGANIZATIONS:
        raise ApiError(
            409,
            "organization_limit_reached",
            f"You can own at most {MAX_OWNED_ORGANIZATIONS} organizations.",
        )

    organization = Organization(name=data.name, slug=_slugify(data.name))
    db.add(organization)
    db.flush()
    membership = OrganizationMember(
        organization_id=organization.id, profile_id=profile.id, role=MemberRole.OWNER
    )
    db.add(membership)
    audit_log.record(
        db,
        organization_id=organization.id,
        actor_id=profile.id,
        action="organization.created",
        entity_type="organization",
        entity_id=organization.id,
        request_id=request_id,
        details={"name": organization.name},
    )
    db.commit()
    db.refresh(membership)
    return membership
