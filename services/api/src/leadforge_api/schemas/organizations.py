from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import StringConstraints

from leadforge_api.schemas.common import ApiModel, InputModel
from leadforge_core.models import MemberRole


class OrganizationCreate(InputModel):
    name: Annotated[str, StringConstraints(min_length=2, max_length=120)]


class OrganizationRead(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    is_development_seed: bool
    created_at: datetime


class MembershipRead(ApiModel):
    role: MemberRole
    organization: OrganizationRead


class ProfileRead(ApiModel):
    id: uuid.UUID
    email: str | None
    full_name: str | None


class MeRead(ApiModel):
    profile: ProfileRead
    memberships: list[MembershipRead]
