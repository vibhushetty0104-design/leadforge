"""Helpers shared by the test-suites of every backend package.

Tests run against ``TEST_DATABASE_URL`` when set (CI uses Postgres) and fall back
to an in-memory SQLite database so ``pytest`` works with zero setup.

Schema here is built with ``create_all`` for speed and deliberately left behind
between runs, so a test database must never double as a migration target. Alembic
alone owns every real schema; migrations are validated by
``scripts/check_migrations.py`` against databases of their own.
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, make_url

from leadforge_core.config import normalize_database_url
from leadforge_core.db import build_engine
from leadforge_core.models import Base

SQLITE_MEMORY_URL = "sqlite+pysqlite:///:memory:"


class UnsafeTestDatabaseError(RuntimeError):
    """The configured test database might hold data worth keeping."""


def _assert_disposable(url: str) -> None:
    """``reset_schema`` drops every table, so refuse anything but a test database."""
    environment = os.environ.get("ENVIRONMENT", "").lower()
    if environment in {"staging", "production"}:
        raise UnsafeTestDatabaseError(f"refusing to run tests with ENVIRONMENT={environment}")
    target = make_url(normalize_database_url(url))
    if "test" not in (target.database or "").lower():
        raise UnsafeTestDatabaseError(
            f"TEST_DATABASE_URL database name must contain 'test', got {target.database!r}"
        )
    application_url = os.environ.get("DATABASE_URL")
    if application_url and make_url(normalize_database_url(application_url)) == target:
        raise UnsafeTestDatabaseError("TEST_DATABASE_URL is the same database as DATABASE_URL")


def resolve_test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return SQLITE_MEMORY_URL
    _assert_disposable(url)
    return url


def make_test_engine() -> Engine:
    return build_engine(resolve_test_database_url(), pool_size=5, max_overflow=5)


def reset_schema(engine: Engine) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def is_postgres(engine: Engine) -> bool:
    return engine.dialect.name == "postgresql"
