from __future__ import annotations

from fastapi import APIRouter, Request, status

from leadforge_api.deps import CurrentProfile, DbSession
from leadforge_api.schemas.organizations import (
    MembershipRead,
    MeRead,
    OrganizationCreate,
    ProfileRead,
)
from leadforge_api.services import organizations as service

router = APIRouter(tags=["account"])


@router.get("/me", response_model=MeRead, summary="Current user and organization memberships")
def read_me(profile: CurrentProfile, db: DbSession) -> MeRead:
    memberships = service.list_memberships(db, profile)
    return MeRead(
        profile=ProfileRead.model_validate(profile),
        memberships=[MembershipRead.model_validate(m) for m in memberships],
    )


@router.post(
    "/organizations",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization owned by the caller",
)
def create_organization(
    body: OrganizationCreate, profile: CurrentProfile, db: DbSession, request: Request
) -> MembershipRead:
    membership = service.create_organization(
        db, profile, body, getattr(request.state, "request_id", None)
    )
    return MembershipRead.model_validate(membership)
