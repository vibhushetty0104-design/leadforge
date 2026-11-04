"""Engine and session construction."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from leadforge_core.config import CoreSettings, normalize_database_url


def build_engine(
    url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 5,
    echo: bool = False,
) -> Engine:
    url = normalize_database_url(url)
    kwargs: dict[str, Any] = {"echo": echo, "future": True}

    if url.startswith("sqlite"):
        # SQLite is only used by the automated test-suite. In-memory databases must
        # share a single connection, otherwise every checkout sees an empty DB.
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url.rstrip("/").endswith("sqlite:"):
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_conn: Any, _record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    kwargs.update(
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        # Supabase's transaction-mode pooler (Supavisor, port 6543) cannot use
        # server-side prepared statements. Disabling them is safe everywhere.
        connect_args={"prepare_threshold": None},
    )
    return create_engine(url, **kwargs)


def engine_from_settings(settings: CoreSettings) -> Engine:
    return build_engine(
        settings.sqlalchemy_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.database_echo,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional scope: commit on success, roll back and re-raise on error."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
