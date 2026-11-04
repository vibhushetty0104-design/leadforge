"""Development seed data.

Creates (or refreshes) a single organization flagged ``is_development_seed`` that
contains clearly fictional businesses on reserved ``example.com`` / ``example.org``
subdomains. The UI labels this organization as seed data everywhere, and nothing
here resembles a real prospect. No audits or lead scores are seeded: those must
only ever come from real measurements.

Usage (from the repository root, with DATABASE_URL exported):

    python database/seeds/seed_dev.py --owner-user-id <your Supabase auth user id>

Refuses to run when ENVIRONMENT is staging or production.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import timedelta

from sqlalchemy import select

from leadforge_core.config import normalize_database_url
from leadforge_core.db import build_engine, build_session_factory, session_scope
from leadforge_core.models import (
    Activity,
    ActivityType,
    Business,
    BusinessStatus,
    Campaign,
    CampaignStatus,
    Contact,
    MemberRole,
    Organization,
    OrganizationMember,
    Profile,
    RecordSource,
)
from leadforge_core.models.base import utcnow

SEED_SLUG = "development-seed"
SEED_NAME = "Development Seed (fictional data)"

# name, subdomain, industry, city, country, status
BUSINESSES = [
    ("Sample Bakery Co.", "bakery.example.com", "Food & Beverage", "Springfield", "US", "new"),
    (
        "Placeholder Plumbing",
        "plumbing.example.com",
        "Home Services",
        "Riverton",
        "US",
        "researching",
    ),
    ("Demo Dental Studio", "dental.example.org", "Healthcare", "Lakeside", "GB", "qualified"),
    ("Example Fitness Hub", "fitness.example.net", "Fitness", "Hillview", "CA", "contacted"),
    ("Fictional Law Partners", "law.example.org", "Legal", "Brookfield", "AU", "engaged"),
    ("Test Pattern Florist", "florist.example.com", "Retail", "Maplewood", "US", "lost"),
]


def _guard_environment() -> None:
    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env in {"staging", "production"}:
        sys.exit(f"Refusing to seed development data into ENVIRONMENT={env}.")


def seed(database_url: str, owner_user_id: uuid.UUID | None) -> None:
    engine = build_engine(normalize_database_url(database_url))
    factory = build_session_factory(engine)
    with session_scope(factory) as db:
        org = db.scalar(select(Organization).where(Organization.slug == SEED_SLUG))
        if org is not None:
            # Rebuild from scratch so the seed stays deterministic.
            db.delete(org)
            db.flush()
        org = Organization(name=SEED_NAME, slug=SEED_SLUG, is_development_seed=True)
        db.add(org)
        db.flush()

        if owner_user_id is not None:
            if db.get(Profile, owner_user_id) is None:
                db.add(Profile(id=owner_user_id))
                db.flush()
            db.add(
                OrganizationMember(
                    organization_id=org.id, profile_id=owner_user_id, role=MemberRole.OWNER
                )
            )

        now = utcnow()
        businesses: list[Business] = []
        for index, (name, host, industry, city, country, status) in enumerate(BUSINESSES):
            business = Business(
                organization_id=org.id,
                name=name,
                website_url=f"https://{host}/",
                domain=host,
                industry=industry,
                city=city,
                country_code=country,
                status=BusinessStatus(status),
                source=RecordSource.DEVELOPMENT_SEED,
                notes="Fictional development seed record.",
                created_at=now - timedelta(days=index * 3),
            )
            db.add(business)
            businesses.append(business)
        db.flush()

        db.add(
            Contact(
                organization_id=org.id,
                business_id=businesses[2].id,
                full_name="Alex Example",
                role_title="Practice Manager",
                email="alex@dental.example.org",
                is_primary=True,
                source=RecordSource.DEVELOPMENT_SEED,
            )
        )
        db.add(
            Campaign(
                organization_id=org.id,
                name="Seed: local services outreach",
                description="Fictional campaign for UI development.",
                status=CampaignStatus.DRAFT,
            )
        )
        db.add_all(
            [
                Activity(
                    organization_id=org.id,
                    business_id=businesses[3].id,
                    type=ActivityType.FOLLOW_UP,
                    summary="Follow up on intro email (seed)",
                    due_at=now - timedelta(days=1),
                ),
                Activity(
                    organization_id=org.id,
                    business_id=businesses[4].id,
                    type=ActivityType.FOLLOW_UP,
                    summary="Send proposal (seed)",
                    due_at=now + timedelta(days=2),
                ),
            ]
        )
    engine.dispose()
    print(f"Seeded organization '{SEED_NAME}' with {len(BUSINESSES)} fictional businesses.")
    if owner_user_id is None:
        print(
            "No --owner-user-id given: sign in, then re-run with your user id to see it in the UI."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--owner-user-id", type=uuid.UUID, help="Supabase auth user id to own the seed org"
    )
    args = parser.parse_args()

    _guard_environment()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set.")
    seed(url, args.owner_user_id)


if __name__ == "__main__":
    main()
