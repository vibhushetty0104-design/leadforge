"""FastAPI dependencies: database sessions, authentication and tenancy.

Authorization model:

* The caller's identity comes only from a verified Supabase access token.
* The active organization comes from the ``X-Organization-Id`` header and is
  accepted only after confirming the caller is a member of it.
* Every data-access function takes the resulting :class:`OrgContext` and scopes
  its queries to ``ctx.organization_id``. Request bodies never carry user or
  organization ids (schemas forbid unknown fields).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from leadforge_api.auth import Principal, SupabaseTokenVerifier
from leadforge_api.errors import ApiError
from leadforge_core.models import MemberRole, OrganizationMember, Profile

_bearer = HTTPBearer(auto_error=False, description="Supabase access token")


def get_db(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(401, "unauthenticated", "Missing bearer access token.")
    verifier: SupabaseTokenVerifier = request.app.state.token_verifier
    return verifier.verify(credentials.credentials)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def get_current_profile(principal: CurrentPrincipal, db: DbSession) -> Profile:
    """Return the caller's profile, creating it on first sight of a new user."""
    profile = db.get(Profile, principal.user_id)
    if profile is None:
        profile = Profile(
            id=principal.user_id, email=principal.email, full_name=principal.full_name
        )
        db.add(profile)
        db.commit()
    elif principal.email and profile.email != principal.email:
        profile.email = principal.email
        db.commit()
    return profile


CurrentProfile = Annotated[Profile, Depends(get_current_profile)]


@dataclass(frozen=True, slots=True)
class OrgContext:
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: MemberRole
    request_id: str | None

    def require_role(self, *roles: MemberRole) -> None:
        if self.role not in roles:
            raise ApiError(403, "insufficient_role", "Your role does not permit this action.")


def get_org_context(
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
    organization_id: Annotated[
        uuid.UUID,
        Header(
            alias="X-Organization-Id", description="Active organization; membership is verified."
        ),
    ],
) -> OrgContext:
    role = db.scalar(
        select(OrganizationMember.role).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.profile_id == principal.user_id,
        )
    )
    if role is None:
        # Same response whether the org does not exist or the caller is not a member,
        # so organization ids cannot be probed.
        raise ApiError(
            403, "organization_access_denied", "You do not have access to this organization."
        )
    return OrgContext(
        organization_id=organization_id,
        user_id=principal.user_id,
        role=role,
        request_id=getattr(request.state, "request_id", None),
    )


CurrentOrg = Annotated[OrgContext, Depends(get_org_context)]
