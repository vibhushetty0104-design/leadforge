"""Configuration shared by every backend service.

Values come exclusively from environment variables (or a local, git-ignored
``.env`` file). Nothing secret has a default.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


def normalize_database_url(url: str) -> str:
    """Force the psycopg 3 driver for Postgres URLs.

    Supabase and most hosts hand out ``postgres://`` or ``postgresql://`` URLs;
    SQLAlchemy would otherwise pick psycopg2, which is not installed.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # `FOO=` in .env means "unset", never "set to the empty string".
        env_ignore_empty=True,
    )

    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    log_json: bool = True

    database_url: SecretStr = Field(
        ..., description="SQLAlchemy URL. postgres:// URLs are rewritten to use psycopg 3."
    )
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=5, ge=0, le=50)
    database_echo: bool = False

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        upper = value.upper()
        if upper not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid log level: {value}")
        return upper

    @property
    def is_production(self) -> bool:
        return self.environment in {Environment.PRODUCTION, Environment.STAGING}

    @property
    def sqlalchemy_url(self) -> str:
        return normalize_database_url(self.database_url.get_secret_value())
