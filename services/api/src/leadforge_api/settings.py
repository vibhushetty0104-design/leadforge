"""API configuration, validated at start-up so misconfiguration fails fast."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import NoDecode

from leadforge_core.config import CoreSettings


class ApiSettings(CoreSettings):
    host: str = "0.0.0.0"  # noqa: S104 - container bind address; exposure is controlled by the platform
    port: int = Field(default=8000, ge=1, le=65535)
    # Proxies whose X-Forwarded-* headers are trusted. Set to your platform's
    # proxy range; "*" is only safe when the API is unreachable except via it.
    forwarded_allow_ips: str = "127.0.0.1"

    # Comma-separated list of exact origins, e.g. "http://localhost:3000,https://app.example.com".
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    supabase_url: str | None = None
    # Legacy HS256 secret. Projects using asymmetric JWT signing keys leave this unset
    # and the API verifies tokens against the project's JWKS endpoint instead.
    supabase_jwt_secret: SecretStr | None = None
    supabase_jwt_audience: str = "authenticated"

    # CSV import limits. The default upload size stays under Vercel's request body
    # limit, because uploads pass through the web app.
    import_max_upload_bytes: int = Field(default=4_000_000, ge=1024, le=100_000_000)
    import_max_rows: int = Field(default=5_000, ge=1, le=100_000)

    # Interactive docs default to on outside production.
    api_docs_enabled: bool | None = None

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def _validate_origins(cls, origins: list[str]) -> list[str]:
        cleaned: list[str] = []
        for origin in origins:
            if origin == "*":
                raise ValueError("wildcard CORS origins are not allowed; list exact origins")
            parts = urlsplit(origin)
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                raise ValueError(f"invalid CORS origin: {origin!r}")
            if parts.path not in {"", "/"} or parts.query or parts.fragment:
                raise ValueError(f"CORS origin must not include a path: {origin!r}")
            cleaned.append(f"{parts.scheme}://{parts.netloc}")
        return cleaned

    @field_validator("supabase_jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        secret = value.get_secret_value()
        if not secret.strip():
            return None  # an empty HMAC key would let anyone forge tokens
        if len(secret) < 32:
            raise ValueError("SUPABASE_JWT_SECRET must be at least 32 characters")
        return value

    @field_validator("supabase_url")
    @classmethod
    def _validate_supabase_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parts = urlsplit(value.strip())
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("SUPABASE_URL must be an http(s) URL")
        return f"{parts.scheme}://{parts.netloc}"

    @model_validator(mode="after")
    def _validate_auth_and_production(self) -> ApiSettings:
        if self.supabase_url is None and self.supabase_jwt_secret is None:
            raise ValueError(
                "Authentication is not configured: set SUPABASE_URL (JWKS verification) "
                "and/or SUPABASE_JWT_SECRET (legacy HS256)."
            )
        if self.is_production:
            if self.supabase_url is None or not self.supabase_url.startswith("https://"):
                raise ValueError("SUPABASE_URL must be an https URL in staging/production")
            insecure = [o for o in self.cors_allowed_origins if o.startswith("http://")]
            if insecure:
                raise ValueError(f"insecure CORS origins in staging/production: {insecure}")
        return self

    @property
    def docs_enabled(self) -> bool:
        return (not self.is_production) if self.api_docs_enabled is None else self.api_docs_enabled

    @property
    def jwt_issuer(self) -> str | None:
        return f"{self.supabase_url}/auth/v1" if self.supabase_url else None

    @property
    def jwks_url(self) -> str | None:
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json" if self.supabase_url else None


@lru_cache(maxsize=1)
def get_settings() -> ApiSettings:
    return ApiSettings()  # populated from the environment
