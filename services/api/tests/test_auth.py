from __future__ import annotations

import uuid
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from leadforge_api.auth import SupabaseTokenVerifier
from leadforge_api.errors import ApiError
from leadforge_api.settings import ApiSettings

from .conftest import SUPABASE_URL, Actor, make_token


def test_missing_token_is_401(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthenticated"
    assert body["error"]["request_id"]
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "token_factory",
    [
        lambda uid: "not-a-jwt",
        lambda uid: make_token(uid, secret="wrong-secret-wrong-secret-wrong-secret"),
        lambda uid: make_token(uid, expires_in=-3600),
        lambda uid: make_token(uid, aud="someone-else"),
        lambda uid: make_token(uid, iss="https://evil.example.com/auth/v1"),
        lambda uid: make_token(uid, role="anon"),
        lambda uid: make_token(uid, sub="not-a-uuid"),
        lambda uid: jwt.encode({"sub": str(uid)}, "", algorithm="none"),
    ],
    ids=[
        "garbage",
        "bad-signature",
        "expired",
        "audience",
        "issuer",
        "anon-role",
        "bad-sub",
        "alg-none",
    ],
)
def test_invalid_tokens_are_rejected(client: TestClient, token_factory) -> None:  # type: ignore[no-untyped-def]
    token = token_factory(uuid.uuid4())
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_provisions_profile_on_first_request(client: TestClient) -> None:
    user_id = uuid.uuid4()
    headers = {"Authorization": f"Bearer {make_token(user_id, email='new@example.com')}"}
    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["profile"] == {"id": str(user_id), "email": "new@example.com", "full_name": None}
    assert body["memberships"] == []


def test_org_header_requires_membership(client: TestClient, owner: Actor, make_actor) -> None:  # type: ignore[no-untyped-def]
    outsider = make_actor()
    headers = {**outsider.headers, "X-Organization-Id": str(owner.organization_id)}
    response = client.get("/api/v1/businesses", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "organization_access_denied"

    # A non-existent organization is indistinguishable from one you cannot access.
    headers["X-Organization-Id"] = str(uuid.uuid4())
    assert client.get("/api/v1/businesses", headers=headers).status_code == 403


def test_org_header_is_required_and_validated(client: TestClient, owner: Actor) -> None:
    headers = {"Authorization": owner.headers["Authorization"]}
    assert client.get("/api/v1/businesses", headers=headers).status_code == 422
    headers["X-Organization-Id"] = "not-a-uuid"
    assert client.get("/api/v1/businesses", headers=headers).status_code == 422


def test_asymmetric_tokens_verify_against_jwks(settings: ApiSettings) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    verifier = SupabaseTokenVerifier(settings)
    verifier._jwks = SimpleNamespace(  # type: ignore[assignment]
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private_key.public_key())
    )
    user_id = uuid.uuid4()
    claims = {
        "sub": str(user_id),
        "aud": "authenticated",
        "role": "authenticated",
        "iss": f"{SUPABASE_URL}/auth/v1",
        "exp": 9999999999,
    }
    token = jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": "k1"})
    assert verifier.verify(token).user_id == user_id

    # An HS256 token signed with the *public* key must not be accepted (alg confusion).
    with pytest.raises(ApiError):
        verifier.verify(make_token(user_id, secret="attacker-chosen-secret-attacker-chosen"))


def test_empty_or_weak_jwt_secret_is_never_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
    monkeypatch.setenv("API_DOCS_ENABLED", "")
    settings = ApiSettings(database_url="sqlite://", supabase_url=SUPABASE_URL)
    assert settings.supabase_jwt_secret is None
    assert settings.docs_enabled is True

    # With no HS256 secret configured, every HS256 token is rejected outright.
    verifier = SupabaseTokenVerifier(settings)
    with pytest.raises(ApiError):
        verifier.verify(
            make_token(uuid.uuid4(), secret="any-attacker-chosen-key-of-sufficient-len")
        )

    with pytest.raises(ValueError, match="at least 32"):
        ApiSettings(
            database_url="sqlite://", supabase_url=SUPABASE_URL, supabase_jwt_secret="short"
        )


def test_settings_require_auth_configuration() -> None:
    with pytest.raises(ValueError, match="Authentication is not configured"):
        ApiSettings(database_url="sqlite://", supabase_url=None, supabase_jwt_secret=None)


def test_settings_reject_wildcard_and_insecure_cors() -> None:
    with pytest.raises(ValueError, match="wildcard"):
        ApiSettings(database_url="sqlite://", supabase_url=SUPABASE_URL, cors_allowed_origins="*")
    with pytest.raises(ValueError, match="insecure CORS"):
        ApiSettings(
            database_url="sqlite://",
            environment="production",
            supabase_url=SUPABASE_URL,
            cors_allowed_origins="http://app.example.com",
        )
