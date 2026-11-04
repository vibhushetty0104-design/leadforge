"""The Alembic chain must build exactly the schema the ORM models describe."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from leadforge_core.models import Base
from leadforge_core.testing import is_postgres

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "database" / "alembic.ini"


@pytest.fixture
def clean_engine(engine: Engine) -> Engine:
    if not is_postgres(engine):
        pytest.skip("migrations target Postgres (set TEST_DATABASE_URL)")
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        conn.execute(text("DROP FUNCTION IF EXISTS leadforge_set_updated_at() CASCADE"))
    return engine


def _run(engine: Engine, action: str, revision: str) -> None:
    cfg = Config(str(ALEMBIC_INI))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        getattr(command, action)(cfg, revision)


def test_upgrade_matches_models_and_downgrade_is_clean(clean_engine: Engine) -> None:
    _run(clean_engine, "upgrade", "head")

    with clean_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == []
        rls = (
            conn.execute(
                text(
                    "SELECT relname FROM pg_class WHERE relkind = 'r' "
                    "AND relnamespace = 'public'::regnamespace AND NOT relrowsecurity"
                )
            )
            .scalars()
            .all()
        )
        assert rls == [], f"tables without RLS: {rls}"

    _run(clean_engine, "downgrade", "base")
    remaining = set(inspect(clean_engine).get_table_names()) - {"alembic_version"}
    assert remaining == set()


def test_updated_at_trigger_fires(clean_engine: Engine) -> None:
    _run(clean_engine, "upgrade", "head")
    try:
        with clean_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (name, slug, created_at, updated_at) "
                    "VALUES ('T', 't', now() - interval '1 day', now() - interval '1 day')"
                )
            )
            conn.execute(text("UPDATE organizations SET name = 'T2' WHERE slug = 't'"))
            age = conn.execute(
                text("SELECT now() - updated_at < interval '1 minute' FROM organizations")
            ).scalar_one()
        assert age is True
    finally:
        _run(clean_engine, "downgrade", "base")
