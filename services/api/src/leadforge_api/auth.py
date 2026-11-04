"""Supabase access-token verification.

Supabase issues JWTs signed either with the project's asymmetric signing keys
(RS256/ES256, published at ``/auth/v1/.well-known/jwks.json``) or, on older
projects, with a shared HS256 secret. Both are supported; the token header's
``alg`` selects the path and each path only accepts its own algorithms, which
prevents algorithm-confusion attacks.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

from leadforge_api.errors import ApiError
from leadforge_api.settings import ApiSettings

logger = logging.getLogger("leadforge.api.auth")

ASYMMETRIC_ALGORITHMS = ("RS256", "ES256")
CLOCK_SKEW_SECONDS = 30


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller, derived solely from a verified token."""

    user_id: uuid.UUID
    email: str | None
    full_name: str | None


def _unauthenticated(message: str = "Invalid or expired access token.") -> ApiError:
    return ApiError(401, "unauthenticated", message)


class SupabaseTokenVerifier:
    def __init__(self, settings: ApiSettings) -> None:
        self._audience = settings.supabase_jwt_audience
        self._issuer = settings.jwt_issuer
        self._secret = (
            settings.supabase_jwt_secret.get_secret_value()
            if settings.supabase_jwt_secret
            else None
        )
        self._jwks = (
            PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=600, timeout=5)
            if settings.jwks_url
            else None
        )

    def _signing_key(self, token: str, alg: str) -> Any:
        if alg == "HS256":
            if self._secret is None:
                raise _unauthenticated()
            return self._secret
        if alg in ASYMMETRIC_ALGORITHMS:
            if self._jwks is None:
                raise _unauthenticated()
            try:
                return self._jwks.get_signing_key_from_jwt(token).key
            except jwt.PyJWKClientConnectionError as exc:
                logger.error("JWKS endpoint unreachable", extra={"error": str(exc)})
                raise ApiError(
                    503, "auth_unavailable", "Authentication service is unavailable."
                ) from exc
            except jwt.PyJWKClientError as exc:
                raise _unauthenticated() from exc
        raise _unauthenticated()

    def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise _unauthenticated() from exc

        alg = str(header.get("alg", ""))
        key = self._signing_key(token, alg)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience=self._audience,
                issuer=self._issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "sub", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise _unauthenticated("Access token has expired.") from exc
        except jwt.InvalidTokenError as exc:
            raise _unauthenticated() from exc

        if claims.get("role") != "authenticated":
            raise _unauthenticated()
        try:
            user_id = uuid.UUID(str(claims["sub"]))
        except ValueError as exc:
            raise _unauthenticated() from exc

        metadata = claims.get("user_metadata")
        full_name = metadata.get("full_name") if isinstance(metadata, dict) else None
        email = claims.get("email")
        return Principal(
            user_id=user_id,
            email=email if isinstance(email, str) and email else None,
            full_name=full_name if isinstance(full_name, str) and full_name else None,
        )
