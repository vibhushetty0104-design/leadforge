from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from leadforge_core.models import (
    Base,
    Business,
    BusinessStatus,
    Contact,
    LeadScore,
    Organization,
    OrganizationMember,
    Profile,
    Suppression,
    SuppressionReason,
)

TENANT_TABLES_EXEMPT = {"profiles", "organizations", "audit_logs"}


def test_every_tenant_table_has_an_organization_fk() -> None:
    for table in Base.metadata.sorted_tables:
        if table.name in TENANT_TABLES_EXEMPT:
            continue
        assert "organization_id" in table.c, table.name
        fks = {fk.target_fullname for fk in table.c.organization_id.foreign_keys}
        assert fks == {"organizations.id"}, table.name
        assert not table.c.organization_id.nullable, table.name


def test_every_table_has_uuid_pk_and_timestamps() -> None:
    for table in Base.metadata.sorted_tables:
        assert [c.name for c in table.primary_key.columns] == ["id"], table.name
        assert "created_at" in table.c, table.name
        if table.name != "audit_logs":  # append-only by design
            assert "updated_at" in table.c, table.name


def test_business_domain_unique_per_org(session: Session, org: Organization) -> None:
    other = Organization(name="Other", slug="other-org")
    session.add(other)
    session.flush()
    session.add_all(
        [
            Business(organization_id=org.id, name="A", domain="acme.example.com"),
            Business(organization_id=other.id, name="A", domain="acme.example.com"),
            Business(organization_id=org.id, name="No site 1"),
            Business(organization_id=org.id, name="No site 2"),
        ]
    )
    session.commit()

    session.add(Business(organization_id=org.id, name="Dup", domain="acme.example.com"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_enum_value_is_rejected(session: Session, org: Organization) -> None:
    business = Business(organization_id=org.id, name="X")
    business.status = "pending"  # type: ignore[assignment]
    session.add(business)
    with pytest.raises((StatementError, LookupError, IntegrityError)):
        session.commit()


def test_business_defaults(session: Session, org: Organization) -> None:
    business = Business(organization_id=org.id, name="Defaults")
    session.add(business)
    session.commit()
    assert business.status == BusinessStatus.NEW
    assert business.created_at is not None


def test_deleting_business_cascades_to_children(session: Session, org: Organization) -> None:
    business = Business(organization_id=org.id, name="Parent")
    session.add(business)
    session.flush()
    session.add(Contact(organization_id=org.id, business_id=business.id, full_name="C"))
    session.add(
        LeadScore(organization_id=org.id, business_id=business.id, score=50, model_version="v0")
    )
    session.commit()

    session.delete(business)
    session.commit()
    assert session.scalars(select(Contact)).all() == []
    assert session.scalars(select(LeadScore)).all() == []


def test_lead_score_range_is_enforced(session: Session, org: Organization) -> None:
    business = Business(organization_id=org.id, name="Scored")
    session.add(business)
    session.flush()
    session.add(
        LeadScore(organization_id=org.id, business_id=business.id, score=101, model_version="v0")
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_suppression_requires_email_or_domain(session: Session, org: Organization) -> None:
    session.add(Suppression(organization_id=org.id, reason=SuppressionReason.MANUAL))
    with pytest.raises(IntegrityError):
        session.commit()


def test_membership_unique_and_cascades_with_org(session: Session, org: Organization) -> None:
    import uuid

    profile = Profile(id=uuid.uuid4(), email="person@example.com")
    session.add(profile)
    session.add(OrganizationMember(organization_id=org.id, profile_id=profile.id))
    session.commit()

    session.add(OrganizationMember(organization_id=org.id, profile_id=profile.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.delete(session.get(Organization, org.id))
    session.commit()
    assert session.scalars(select(OrganizationMember)).all() == []
