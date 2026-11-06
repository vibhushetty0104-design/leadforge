"""Alembic owns the schema; ORM table creation is confined to disposable test databases."""

from __future__ import annotations

from pathlib import Path

import pytest

from leadforge_core.testing import UnsafeTestDatabaseError, resolve_test_database_url

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOTS = ("packages/core/src", "services/api/src", "services/worker/src")


def test_create_all_only_exists_in_the_test_helper() -> None:
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for root in SOURCE_ROOTS
        for path in (REPO_ROOT / root).rglob("*.py")
        if "create_all(" in path.read_text(encoding="utf-8") and path.name != "testing.py"
    ]
    assert offenders == []


def test_defaults_to_in_memory_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert "memory" in resolve_test_database_url()


def test_accepts_a_database_named_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "postgresql://ci:ci@localhost:5432/leadforge_test"
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert resolve_test_database_url() == url


@pytest.mark.parametrize(
    "url", ["postgresql://u:p@db.example.com:5432/postgres", "postgres://u:p@host/leadforge"]
)
def test_refuses_databases_not_named_for_tests(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    with pytest.raises(UnsafeTestDatabaseError, match="must contain 'test'"):
        resolve_test_database_url()


def test_refuses_the_application_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "postgres://u:p@host/app_test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/app_test")
    with pytest.raises(UnsafeTestDatabaseError, match="same database"):
        resolve_test_database_url()


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_refuses_deployed_environments(monkeypatch: pytest.MonkeyPatch, environment: str) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://u:p@host/app_test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", environment)
    with pytest.raises(UnsafeTestDatabaseError, match="ENVIRONMENT"):
        resolve_test_database_url()
