"""Alembic environment. Targets Postgres (local Docker or Supabase)."""

from __future__ import annotations

import os
from typing import Any, Literal

from alembic import context
from sqlalchemy import JSON, create_engine, pool

from leadforge_core.config import normalize_database_url
from leadforge_core.models import Base
from leadforge_core.models.base import UTCDateTime

config = context.config
target_metadata = Base.metadata


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | Literal[False]:
    """Render application column types as plain SQLAlchemy types.

    Migrations must not import application code that may change later.
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    if type_ == "type" and isinstance(obj, JSON):
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return "postgresql.JSONB()"
    return False


CONFIGURE_KWARGS: dict[str, Any] = {
    "target_metadata": target_metadata,
    "compare_type": True,
    "render_item": render_item,
}


def _database_url() -> str:
    url = config.attributes.get("database_url") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set; export it before running migrations.")
    return normalize_database_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **CONFIGURE_KWARGS,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, **CONFIGURE_KWARGS)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(
        _database_url(),
        poolclass=pool.NullPool,
        # Compatible with Supabase's transaction pooler (no prepared statements).
        connect_args={"prepare_threshold": None},
    )
    with engine.connect() as conn:
        context.configure(connection=conn, **CONFIGURE_KWARGS)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
