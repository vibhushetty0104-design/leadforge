"""Helpers shared by the test-suites of every backend package.

Tests run against ``TEST_DATABASE_URL`` when set (CI uses Postgres) and fall back
to an in-memory SQLite database so ``pytest`` works with zero setup.
"""

from __future__ import annotations

import os

from sqlalchemy import Engine

from leadforge_core.db import build_engine
from leadforge_core.models import Base

SQLITE_MEMORY_URL = "sqlite+pysqlite:///:memory:"


def resolve_test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL") or SQLITE_MEMORY_URL


def make_test_engine() -> Engine:
    return build_engine(resolve_test_database_url(), pool_size=5, max_overflow=5)


def reset_schema(engine: Engine) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def is_postgres(engine: Engine) -> bool:
    return engine.dialect.name == "postgresql"
