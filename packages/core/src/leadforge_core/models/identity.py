"""Users, organizations and memberships."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint, Uuid, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from leadforge_core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from leadforge_core.models.enums import MemberRole


class Profile(TimestampMixin, Base):
    """Application profile for an authenticated user.

    ``id`` equals the Supabase ``auth.users.id`` (the JWT ``sub`` claim). The FK to
    ``auth.users`` is added only on Supabase (see database/supabase/), because the
    ``auth`` schema does not exist on plain Postgres.
    """

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    full_name: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))

    memberships: Mapped[list[OrganizationMember]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index("ix_profiles_email_lower", func.lower(email)),)


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    # Rows inside a development-seed organization are fictional demo data and are
    # always labelled as such in the UI. Production records never live here.
    is_development_seed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    members: Mapped[list[OrganizationMember]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )


class OrganizationMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_members"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MemberRole] = mapped_column(
        str_enum(MemberRole, "member_role"), nullable=False, default=MemberRole.MEMBER
    )

    organization: Mapped[Organization] = relationship(back_populates="members")
    profile: Mapped[Profile] = relationship(back_populates="memberships")

    __table_args__ = (UniqueConstraint("organization_id", "profile_id"),)
