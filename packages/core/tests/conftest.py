from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from leadforge_core.db import build_session_factory
from leadforge_core.models import Organization
from leadforge_core.testing import make_test_engine, reset_schema


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    eng = make_test_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    reset_schema(engine)
    return build_session_factory(engine)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as s:
        yield s


@pytest.fixture
def org(session: Session) -> Organization:
    organization = Organization(name="Test Org", slug=f"test-{uuid.uuid4().hex[:8]}")
    session.add(organization)
    session.commit()
    return organization
