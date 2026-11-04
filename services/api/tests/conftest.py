from __future__ import annotations

import secrets
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from leadforge_api.main import create_app
from leadforge_api.settings import ApiSettings
from leadforge_core.db import build_session_factory
from leadforge_core.models import MemberRole, Organization, OrganizationMember, Profile
from leadforge_core.testing import make_test_engine, reset_schema, resolve_test_database_url

SUPABASE_URL = "https://project-ref.supabase.co"
# Generated per test session; never a real or committed credential.
JWT_SECRET = secrets.token_urlsafe(48)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    eng = make_test_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def settings() -> ApiSettings:
    return ApiSettings(
        environment="test",
        database_url=resolve_test_database_url(),
        supabase_url=SUPABASE_URL,
        supabase_jwt_secret=JWT_SECRET,
        cors_allowed_origins="http://localhost:3000",
        log_json=False,
        log_level="WARNING",
    )


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    reset_schema(engine)
    return build_session_factory(engine)


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def client(
    settings: ApiSettings, engine: Engine, session_factory: sessionmaker[Session]
) -> TestClient:
    return TestClient(create_app(settings, engine=engine))


def make_token(
    user_id: uuid.UUID,
    *,
    email: str = "user@example.com",
    secret: str = JWT_SECRET,
    expires_in: int = 3600,
    **overrides: Any,
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "iss": f"{SUPABASE_URL}/auth/v1",
        "iat": now,
        "exp": now + expires_in,
    }
    claims.update(overrides)
    return jwt.encode(claims, secret, algorithm="HS256")


class Actor:
    """A user with a membership, plus helpers to build authenticated headers."""

    def __init__(self, user_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.organization_id = organization_id

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {make_token(self.user_id)}",
            "X-Organization-Id": str(self.organization_id),
        }


@pytest.fixture
def make_actor(db: Session) -> Callable[..., Actor]:
    def _make(
        role: MemberRole = MemberRole.OWNER, organization: Organization | None = None
    ) -> Actor:
        if organization is None:
            organization = Organization(name="Acme Agency", slug=f"acme-{uuid.uuid4().hex[:8]}")
            db.add(organization)
            db.flush()
        profile = Profile(id=uuid.uuid4(), email=f"{uuid.uuid4().hex[:6]}@example.com")
        db.add(profile)
        db.flush()
        db.add(
            OrganizationMember(organization_id=organization.id, profile_id=profile.id, role=role)
        )
        db.commit()
        return Actor(profile.id, organization.id)

    return _make


@pytest.fixture
def owner(make_actor: Callable[..., Actor]) -> Actor:
    return make_actor()
