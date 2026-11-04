"""Initial schema: tenancy, prospects, audits, scoring, jobs, outreach, CRM, audit log.

Revision ID: 0001
Revises:
Create Date: 2026-11-03 22:54:53.269770+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables carrying an updated_at column maintained by trigger (covers writes that
# bypass the ORM, e.g. the Supabase SQL editor).
UPDATED_AT_TABLES = (
    "profiles",
    "organizations",
    "organization_members",
    "businesses",
    "contacts",
    "website_audits",
    "audit_findings",
    "lead_scores",
    "jobs",
    "campaigns",
    "email_drafts",
    "suppressions",
    "activities",
)
ALL_TABLES = (*UPDATED_AT_TABLES, "audit_logs")


def _create_support_objects() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION leadforge_set_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$;
        """
    )
    for table in UPDATED_AT_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION leadforge_set_updated_at()"
        )
    # Row Level Security is enabled on every table with *no* policies, i.e. deny
    # by default for Supabase's anon/authenticated roles via the Data API. The
    # backend connects as the table owner and enforces tenancy itself. Optional
    # membership-based policies for direct client access live in
    # database/supabase/policies.sql.
    # alembic_version is included so Supabase does not expose it either.
    for table in (*ALL_TABLES, "alembic_version"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column(
            "is_development_seed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("slug", name=op.f("uq_organizations_slug")),
    )
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("avatar_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profiles")),
    )
    op.create_index(
        "ix_profiles_email_lower", "profiles", [sa.literal_column("lower(email)")], unique=False
    )
    op.create_table(
        "audit_logs",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["profiles.id"],
            name=op.f("fk_audit_logs_actor_id_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_audit_logs_organization_id_organizations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index(
        "ix_audit_logs_org_created_at",
        "audit_logs",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_logs_organization_id"), "audit_logs", ["organization_id"], unique=False
    )
    op.create_table(
        "businesses",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        sa.Column("domain", sa.String(length=253), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "researching",
                "qualified",
                "contacted",
                "engaged",
                "won",
                "lost",
                "disqualified",
                name="business_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="new",
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "manual",
                "csv_import",
                "development_seed",
                name="business_source",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["profiles.id"],
            name=op.f("fk_businesses_created_by_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_businesses_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_businesses")),
    )
    op.create_index(
        "ix_businesses_org_created_at",
        "businesses",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_businesses_org_status", "businesses", ["organization_id", "status"], unique=False
    )
    op.create_index(
        op.f("ix_businesses_organization_id"), "businesses", ["organization_id"], unique=False
    )
    op.create_index(
        "uq_businesses_organization_id_domain",
        "businesses",
        ["organization_id", "domain"],
        unique=True,
        postgresql_where=sa.text("domain IS NOT NULL"),
    )
    op.create_table(
        "campaigns",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "active",
                "paused",
                "completed",
                "archived",
                name="campaign_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["profiles.id"],
            name=op.f("fk_campaigns_created_by_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_campaigns_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaigns")),
        sa.UniqueConstraint(
            "organization_id", "name", name=op.f("uq_campaigns_organization_id_name")
        ),
    )
    op.create_index(
        "ix_campaigns_org_status", "campaigns", ["organization_id", "status"], unique=False
    )
    op.create_index(
        op.f("ix_campaigns_organization_id"), "campaigns", ["organization_id"], unique=False
    )
    op.create_table(
        "jobs",
        sa.Column(
            "type",
            sa.Enum(
                "website_audit",
                "lead_scoring",
                "import",
                name="job_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "completed",
                "failed",
                name="job_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.String(length=200), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_jobs_attempts_non_negative")),
        sa.CheckConstraint("max_attempts >= 1", name=op.f("ck_jobs_max_attempts_positive")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["profiles.id"],
            name=op.f("fk_jobs_created_by_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_jobs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index("ix_jobs_claim", "jobs", ["status", "priority", "run_after"], unique=False)
    op.create_index("ix_jobs_lease_expires_at", "jobs", ["lease_expires_at"], unique=False)
    op.create_index("ix_jobs_org_status", "jobs", ["organization_id", "status"], unique=False)
    op.create_index(op.f("ix_jobs_organization_id"), "jobs", ["organization_id"], unique=False)
    op.create_table(
        "organization_members",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "owner",
                "admin",
                "member",
                name="member_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_members_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_organization_members_profile_id_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_members")),
        sa.UniqueConstraint(
            "organization_id",
            "profile_id",
            name=op.f("uq_organization_members_organization_id_profile_id"),
        ),
    )
    op.create_index(
        op.f("ix_organization_members_profile_id"),
        "organization_members",
        ["profile_id"],
        unique=False,
    )
    op.create_table(
        "suppressions",
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("domain", sa.String(length=253), nullable=True),
        sa.Column(
            "reason",
            sa.Enum(
                "unsubscribed",
                "bounced",
                "complaint",
                "do_not_contact",
                "manual",
                name="suppression_reason",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "email IS NOT NULL OR domain IS NOT NULL", name=op.f("ck_suppressions_email_or_domain")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["profiles.id"],
            name=op.f("fk_suppressions_created_by_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_suppressions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppressions")),
    )
    op.create_index(
        op.f("ix_suppressions_organization_id"), "suppressions", ["organization_id"], unique=False
    )
    op.create_index(
        "uq_suppressions_organization_id_domain",
        "suppressions",
        ["organization_id", "domain"],
        unique=True,
        postgresql_where=sa.text("domain IS NOT NULL"),
    )
    op.create_index(
        "uq_suppressions_organization_id_email",
        "suppressions",
        ["organization_id", "email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_table(
        "contacts",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("role_title", sa.String(length=120), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("profile_url", sa.String(length=2048), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "manual",
                "csv_import",
                "development_seed",
                name="contact_source",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_contacts_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_contacts_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
    )
    op.create_index(op.f("ix_contacts_business_id"), "contacts", ["business_id"], unique=False)
    op.create_index("ix_contacts_org_email", "contacts", ["organization_id", "email"], unique=False)
    op.create_index(
        op.f("ix_contacts_organization_id"), "contacts", ["organization_id"], unique=False
    )
    op.create_table(
        "website_audits",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("requested_url", sa.String(length=2048), nullable=False),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "completed",
                "failed",
                name="audit_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_website_audits_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_website_audits_job_id_jobs"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_website_audits_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["profiles.id"],
            name=op.f("fk_website_audits_requested_by_profiles"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_website_audits")),
    )
    op.create_index(
        op.f("ix_website_audits_business_id"), "website_audits", ["business_id"], unique=False
    )
    op.create_index(op.f("ix_website_audits_job_id"), "website_audits", ["job_id"], unique=False)
    op.create_index(
        "ix_website_audits_org_status",
        "website_audits",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_website_audits_organization_id"),
        "website_audits",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "activities",
        sa.Column("business_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column(
            "type",
            sa.Enum(
                "note",
                "call",
                "email_sent",
                "email_received",
                "meeting",
                "status_change",
                "follow_up",
                name="activity_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["profiles.id"],
            name=op.f("fk_activities_actor_id_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_activities_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name=op.f("fk_activities_campaign_id_campaigns"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_activities_contact_id_contacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_activities_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activities")),
    )
    op.create_index(op.f("ix_activities_business_id"), "activities", ["business_id"], unique=False)
    op.create_index(
        "ix_activities_org_due_at", "activities", ["organization_id", "due_at"], unique=False
    )
    op.create_index(
        "ix_activities_org_occurred_at",
        "activities",
        ["organization_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_activities_organization_id"), "activities", ["organization_id"], unique=False
    )
    op.create_table(
        "audit_findings",
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "performance",
                "seo",
                "accessibility",
                "conversion",
                "security",
                "content",
                "technical",
                name="finding_category",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "info",
                "low",
                "medium",
                "high",
                "critical",
                name="finding_severity",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["audit_id"],
            ["website_audits.id"],
            name=op.f("fk_audit_findings_audit_id_website_audits"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_audit_findings_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_findings")),
    )
    op.create_index(
        op.f("ix_audit_findings_audit_id"), "audit_findings", ["audit_id"], unique=False
    )
    op.create_index(
        "ix_audit_findings_audit_severity", "audit_findings", ["audit_id", "severity"], unique=False
    )
    op.create_index(
        op.f("ix_audit_findings_organization_id"),
        "audit_findings",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "email_drafts",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "approved",
                "sent",
                "discarded",
                name="email_draft_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_email_drafts_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name=op.f("fk_email_drafts_campaign_id_campaigns"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_email_drafts_contact_id_contacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["profiles.id"],
            name=op.f("fk_email_drafts_created_by_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_email_drafts_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_drafts")),
    )
    op.create_index(
        op.f("ix_email_drafts_business_id"), "email_drafts", ["business_id"], unique=False
    )
    op.create_index(
        op.f("ix_email_drafts_campaign_id"), "email_drafts", ["campaign_id"], unique=False
    )
    op.create_index(
        op.f("ix_email_drafts_contact_id"), "email_drafts", ["contact_id"], unique=False
    )
    op.create_index(
        "ix_email_drafts_org_status", "email_drafts", ["organization_id", "status"], unique=False
    )
    op.create_index(
        op.f("ix_email_drafts_organization_id"), "email_drafts", ["organization_id"], unique=False
    )
    op.create_table(
        "lead_scores",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column("breakdown", postgresql.JSONB(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name=op.f("ck_lead_scores_score_range")),
        sa.ForeignKeyConstraint(
            ["audit_id"],
            ["website_audits.id"],
            name=op.f("fk_lead_scores_audit_id_website_audits"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_lead_scores_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_lead_scores_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_scores")),
    )
    op.create_index(op.f("ix_lead_scores_audit_id"), "lead_scores", ["audit_id"], unique=False)
    op.create_index(
        "ix_lead_scores_business_computed_at",
        "lead_scores",
        ["business_id", "computed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_lead_scores_organization_id"), "lead_scores", ["organization_id"], unique=False
    )
    _create_support_objects()


def downgrade() -> None:
    op.drop_index(op.f("ix_lead_scores_organization_id"), table_name="lead_scores")
    op.drop_index("ix_lead_scores_business_computed_at", table_name="lead_scores")
    op.drop_index(op.f("ix_lead_scores_audit_id"), table_name="lead_scores")
    op.drop_table("lead_scores")
    op.drop_index(op.f("ix_email_drafts_organization_id"), table_name="email_drafts")
    op.drop_index("ix_email_drafts_org_status", table_name="email_drafts")
    op.drop_index(op.f("ix_email_drafts_contact_id"), table_name="email_drafts")
    op.drop_index(op.f("ix_email_drafts_campaign_id"), table_name="email_drafts")
    op.drop_index(op.f("ix_email_drafts_business_id"), table_name="email_drafts")
    op.drop_table("email_drafts")
    op.drop_index(op.f("ix_audit_findings_organization_id"), table_name="audit_findings")
    op.drop_index("ix_audit_findings_audit_severity", table_name="audit_findings")
    op.drop_index(op.f("ix_audit_findings_audit_id"), table_name="audit_findings")
    op.drop_table("audit_findings")
    op.drop_index(op.f("ix_activities_organization_id"), table_name="activities")
    op.drop_index("ix_activities_org_occurred_at", table_name="activities")
    op.drop_index("ix_activities_org_due_at", table_name="activities")
    op.drop_index(op.f("ix_activities_business_id"), table_name="activities")
    op.drop_table("activities")
    op.drop_index(op.f("ix_website_audits_organization_id"), table_name="website_audits")
    op.drop_index("ix_website_audits_org_status", table_name="website_audits")
    op.drop_index(op.f("ix_website_audits_job_id"), table_name="website_audits")
    op.drop_index(op.f("ix_website_audits_business_id"), table_name="website_audits")
    op.drop_table("website_audits")
    op.drop_index(op.f("ix_contacts_organization_id"), table_name="contacts")
    op.drop_index("ix_contacts_org_email", table_name="contacts")
    op.drop_index(op.f("ix_contacts_business_id"), table_name="contacts")
    op.drop_table("contacts")
    op.drop_index(
        "uq_suppressions_organization_id_email",
        table_name="suppressions",
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.drop_index(
        "uq_suppressions_organization_id_domain",
        table_name="suppressions",
        postgresql_where=sa.text("domain IS NOT NULL"),
    )
    op.drop_index(op.f("ix_suppressions_organization_id"), table_name="suppressions")
    op.drop_table("suppressions")
    op.drop_index(op.f("ix_organization_members_profile_id"), table_name="organization_members")
    op.drop_table("organization_members")
    op.drop_index(op.f("ix_jobs_organization_id"), table_name="jobs")
    op.drop_index("ix_jobs_org_status", table_name="jobs")
    op.drop_index("ix_jobs_lease_expires_at", table_name="jobs")
    op.drop_index("ix_jobs_claim", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_campaigns_organization_id"), table_name="campaigns")
    op.drop_index("ix_campaigns_org_status", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_index(
        "uq_businesses_organization_id_domain",
        table_name="businesses",
        postgresql_where=sa.text("domain IS NOT NULL"),
    )
    op.drop_index(op.f("ix_businesses_organization_id"), table_name="businesses")
    op.drop_index("ix_businesses_org_status", table_name="businesses")
    op.drop_index("ix_businesses_org_created_at", table_name="businesses")
    op.drop_table("businesses")
    op.drop_index(op.f("ix_audit_logs_organization_id"), table_name="audit_logs")
    op.drop_index("ix_audit_logs_org_created_at", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_profiles_email_lower", table_name="profiles")
    op.drop_table("profiles")
    op.drop_table("organizations")
    op.execute("DROP FUNCTION IF EXISTS leadforge_set_updated_at()")
