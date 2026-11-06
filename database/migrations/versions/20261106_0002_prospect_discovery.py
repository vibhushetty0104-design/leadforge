"""Prospect discovery: imports, website inspections, job progress and deduplication.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-06 14:16:01.875970+00:00
"""

import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = ("import_batches", "import_rows", "website_inspections")
_LEGAL_SUFFIXES = frozenset(
    [
        "ltd",
        "limited",
        "llc",
        "llp",
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "gmbh",
        "ag",
        "sarl",
        "srl",
        "bv",
        "pty",
        "plc",
        "pvt",
        "private",
        "oy",
        "ab",
        "as",
        "sa",
    ]
)


def _name_key(name: str) -> str | None:
    """Frozen copy of the name normaliser: migrations must not import application code."""
    decomposed = unicodedata.normalize("NFKD", name)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
    words = re.sub(r"[^\w]+", " ", plain.replace("&", " and ")).split()
    while len(words) > 1 and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)[:200] or None


def _job_type_check(*job_types: str) -> None:
    op.execute("ALTER TABLE jobs DROP CONSTRAINT ck_jobs_job_type")
    allowed = ", ".join(f"'{value}'" for value in job_types)
    op.execute(f"ALTER TABLE jobs ADD CONSTRAINT ck_jobs_job_type CHECK (type IN ({allowed}))")


def _backfill_businesses() -> None:
    bind = op.get_bind()
    op.execute("UPDATE businesses SET website_url_original = website_url")
    rows = bind.execute(sa.text("SELECT id, name FROM businesses")).all()
    for business_id, name in rows:
        bind.execute(
            sa.text("UPDATE businesses SET name_key = :key WHERE id = :id"),
            {"key": _name_key(name), "id": business_id},
        )


def _secure_new_tables() -> None:
    for table in NEW_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION leadforge_set_updated_at()"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "queued",
                "running",
                "completed",
                "failed",
                "cancelled",
                name="import_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("headers", postgresql.JSONB(), nullable=False),
        sa.Column("column_mapping", postgresql.JSONB(), nullable=True),
        sa.Column(
            "duplicate_policy",
            sa.Enum(
                "skip",
                "update",
                "create",
                name="import_duplicate_policy",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="skip",
            nullable=False,
        ),
        sa.Column(
            "validate_websites", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("invalid_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("review_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("warning_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_import_batches_created_by_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_import_batches_job_id_jobs"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_import_batches_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
    )
    op.create_index(op.f("ix_import_batches_job_id"), "import_batches", ["job_id"], unique=False)
    op.create_index(
        "ix_import_batches_org_created_at",
        "import_batches",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_import_batches_org_status",
        "import_batches",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_import_batches_organization_id"),
        "import_batches",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "import_rows",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(), nullable=False),
        sa.Column("normalized", postgresql.JSONB(), nullable=True),
        sa.Column("errors", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.Column("duplicate", postgresql.JSONB(), nullable=True),
        sa.Column("has_duplicate", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "pending",
                "invalid",
                "created",
                "updated",
                "skipped_duplicate",
                "needs_review",
                name="import_row_outcome",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "resolution",
            sa.Enum(
                "skip",
                "update",
                "create",
                name="import_row_resolution",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("business_id", sa.Uuid(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_import_rows_batch_id_import_batches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_import_rows_business_id_businesses"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_import_rows_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_rows")),
        sa.UniqueConstraint(
            "batch_id", "row_number", name=op.f("uq_import_rows_batch_id_row_number")
        ),
    )
    op.create_index(
        "ix_import_rows_batch_outcome", "import_rows", ["batch_id", "outcome"], unique=False
    )
    op.create_index(
        op.f("ix_import_rows_business_id"), "import_rows", ["business_id"], unique=False
    )
    op.create_index(
        op.f("ix_import_rows_organization_id"), "import_rows", ["organization_id"], unique=False
    )
    op.create_table(
        "website_inspections",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "success",
                "failed",
                "blocked",
                name="inspection_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("requested_url", sa.String(length=2048), nullable=False),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column("redirect_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("response_bytes", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("meta_description", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.String(length=2048), nullable=True),
        sa.Column("language", sa.String(length=35), nullable=True),
        sa.Column("headings", postgresql.JSONB(), nullable=False),
        sa.Column("contact_links", postgresql.JSONB(), nullable=False),
        sa.Column("emails", postgresql.JSONB(), nullable=False),
        sa.Column("phones", postgresql.JSONB(), nullable=False),
        sa.Column("social_links", postgresql.JSONB(), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
            name=op.f("fk_website_inspections_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_website_inspections_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_website_inspections_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_website_inspections")),
    )
    op.create_index(
        "ix_website_inspections_business_fetched",
        "website_inspections",
        ["business_id", "fetched_at"],
        unique=False,
    )
    op.create_index(
        "ix_website_inspections_domain_fetched",
        "website_inspections",
        ["domain", "fetched_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_website_inspections_job_id"), "website_inspections", ["job_id"], unique=False
    )
    op.create_index(
        op.f("ix_website_inspections_organization_id"),
        "website_inspections",
        ["organization_id"],
        unique=False,
    )
    op.add_column(
        "businesses", sa.Column("website_url_original", sa.String(length=2048), nullable=True)
    )
    op.add_column(
        "businesses",
        sa.Column("domain_discriminator", sa.String(length=64), server_default="", nullable=False),
    )
    op.add_column("businesses", sa.Column("name_key", sa.String(length=200), nullable=True))
    op.add_column("businesses", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("businesses", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("businesses", sa.Column("source_url", sa.String(length=2048), nullable=True))
    op.add_column(
        "businesses",
        sa.Column(
            "website_status",
            sa.Enum(
                "unknown",
                "reachable",
                "unreachable",
                "blocked",
                name="website_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column(
        "businesses", sa.Column("website_checked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "businesses", sa.Column("last_inspected_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("businesses", sa.Column("import_batch_id", sa.Uuid(), nullable=True))
    op.drop_index(
        op.f("uq_businesses_organization_id_domain"),
        table_name="businesses",
        postgresql_where="(domain IS NOT NULL)",
    )
    op.create_index(
        "uq_businesses_organization_id_domain",
        "businesses",
        ["organization_id", "domain", "domain_discriminator"],
        unique=True,
        postgresql_where=sa.text("domain IS NOT NULL"),
    )
    op.create_index(
        op.f("ix_businesses_import_batch_id"), "businesses", ["import_batch_id"], unique=False
    )
    op.create_index(
        "ix_businesses_org_name_key", "businesses", ["organization_id", "name_key"], unique=False
    )
    op.create_index(
        "ix_businesses_org_website_status",
        "businesses",
        ["organization_id", "website_status"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_businesses_import_batch_id_import_batches"),
        "businesses",
        "import_batches",
        ["import_batch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "jobs", sa.Column("progress_current", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("jobs", sa.Column("progress_total", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("dedupe_key", sa.String(length=120), nullable=True))
    op.create_index(
        "uq_jobs_active_dedupe_key",
        "jobs",
        ["organization_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL AND status IN ('queued', 'running')"),
    )

    _job_type_check(
        "website_audit", "lead_scoring", "import", "url_validation", "website_inspection"
    )
    _backfill_businesses()
    _secure_new_tables()


def downgrade() -> None:
    op.execute("DELETE FROM jobs WHERE type IN ('url_validation', 'website_inspection')")
    _job_type_check("website_audit", "lead_scoring", "import")
    # The previous unique index allows one business per domain. Records kept
    # separate on a shared domain survive, without the domain link.
    op.execute("UPDATE businesses SET domain = NULL WHERE domain_discriminator <> ''")
    op.drop_index(
        "uq_jobs_active_dedupe_key",
        table_name="jobs",
        postgresql_where=sa.text("dedupe_key IS NOT NULL AND status IN ('queued', 'running')"),
    )
    op.drop_column("jobs", "dedupe_key")
    op.drop_column("jobs", "progress_total")
    op.drop_column("jobs", "progress_current")
    op.drop_constraint(
        op.f("fk_businesses_import_batch_id_import_batches"), "businesses", type_="foreignkey"
    )
    op.drop_index("ix_businesses_org_website_status", table_name="businesses")
    op.drop_index("ix_businesses_org_name_key", table_name="businesses")
    op.drop_index(op.f("ix_businesses_import_batch_id"), table_name="businesses")
    op.drop_index(
        "uq_businesses_organization_id_domain",
        table_name="businesses",
        postgresql_where=sa.text("domain IS NOT NULL"),
    )
    op.create_index(
        op.f("uq_businesses_organization_id_domain"),
        "businesses",
        ["organization_id", "domain"],
        unique=True,
        postgresql_where="(domain IS NOT NULL)",
    )
    op.drop_column("businesses", "import_batch_id")
    op.drop_column("businesses", "last_inspected_at")
    op.drop_column("businesses", "website_checked_at")
    op.drop_column("businesses", "website_status")
    op.drop_column("businesses", "source_url")
    op.drop_column("businesses", "description")
    op.drop_column("businesses", "email")
    op.drop_column("businesses", "name_key")
    op.drop_column("businesses", "domain_discriminator")
    op.drop_column("businesses", "website_url_original")
    op.drop_index(op.f("ix_website_inspections_organization_id"), table_name="website_inspections")
    op.drop_index(op.f("ix_website_inspections_job_id"), table_name="website_inspections")
    op.drop_index("ix_website_inspections_domain_fetched", table_name="website_inspections")
    op.drop_index("ix_website_inspections_business_fetched", table_name="website_inspections")
    op.drop_table("website_inspections")
    op.drop_index(op.f("ix_import_rows_organization_id"), table_name="import_rows")
    op.drop_index(op.f("ix_import_rows_business_id"), table_name="import_rows")
    op.drop_index("ix_import_rows_batch_outcome", table_name="import_rows")
    op.drop_table("import_rows")
    op.drop_index(op.f("ix_import_batches_organization_id"), table_name="import_batches")
    op.drop_index("ix_import_batches_org_status", table_name="import_batches")
    op.drop_index("ix_import_batches_org_created_at", table_name="import_batches")
    op.drop_index(op.f("ix_import_batches_job_id"), table_name="import_batches")
    op.drop_table("import_batches")
