"""Validate the full Alembic lifecycle against brand-new, throwaway databases.

For each round this creates a uniquely named database, verifies it is empty, runs
the real Alembic CLI (upgrade, check, downgrade) and verifies the schema at each
step. It then drops that database. It never touches any other database, so it is
safe by construction: the only database it can drop is one it just created.

    python scripts/check_migrations.py --admin-url postgresql://user:pass@host:5432/postgres

The URL only needs permission to create databases; ``MIGRATION_CHECK_ADMIN_URL``
may be used instead of the flag. Refuses to run in staging or production.
"""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, make_url, pool, text

from leadforge_core.config import normalize_database_url
from leadforge_core.models import Base

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "database" / "alembic.ini"
SUPPORT_FUNCTION = "leadforge_set_updated_at"


class LifecycleError(RuntimeError):
    pass


def _engine(url: str) -> Engine:
    return create_engine(url, poolclass=pool.NullPool, isolation_level="AUTOCOMMIT")


def _public_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names(schema="public"))


def _scalar(engine: Engine, sql: str) -> object:
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LifecycleError(message)
    print(f"  ok: {message}")


def _alembic(url: str, *args: str) -> None:
    print(f"  $ alembic {' '.join(args)}")
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise LifecycleError(f"alembic {args[0]} failed:\n{result.stdout}\n{result.stderr}")


def run_lifecycle(url: str, expected_tables: set[str], head: str) -> None:
    engine = _engine(url)
    try:
        _require(_public_tables(engine) == set(), "database starts with no tables")

        _alembic(url, "upgrade", "head")
        tables = _public_tables(engine)
        missing = expected_tables - tables
        _require(
            not missing, f"all {len(expected_tables)} application tables exist {missing or ''}"
        )
        version = _scalar(engine, "SELECT string_agg(version_num, ',') FROM alembic_version")
        _require(version == head, f"migrated exactly once to head {head}")

        _alembic(url, "check")
        _require(True, "alembic check reports no drift from the models")

        _alembic(url, "downgrade", "base")
        leftovers = _public_tables(engine) - {"alembic_version"}
        _require(not leftovers, f"application tables removed {leftovers or ''}")
        rows = _scalar(engine, "SELECT count(*) FROM alembic_version")
        _require(rows == 0, "alembic_version is empty")
        functions = _scalar(
            engine, f"SELECT count(*) FROM pg_proc WHERE proname = '{SUPPORT_FUNCTION}'"
        )
        _require(functions == 0, "support function removed")
    finally:
        engine.dispose()


def with_throwaway_database(admin_url: str, action: Callable[[str], None]) -> None:
    # hex-only suffix, so the name is safe to interpolate into DDL
    name = f"leadforge_migcheck_{secrets.token_hex(6)}"
    admin = _engine(admin_url)
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        print(f"created throwaway database {name}")
        try:
            action(make_url(admin_url).set(database=name).render_as_string(hide_password=False))
        finally:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
            print(f"dropped throwaway database {name}")
    finally:
        admin.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--admin-url", default=os.environ.get("MIGRATION_CHECK_ADMIN_URL"))
    parser.add_argument("--rounds", type=int, default=2, choices=range(1, 6), metavar="1-5")
    args = parser.parse_args()

    if os.environ.get("ENVIRONMENT", "development").lower() in {"staging", "production"}:
        sys.exit("Refusing to run migration checks in staging or production.")
    if not args.admin_url:
        sys.exit("Provide --admin-url or MIGRATION_CHECK_ADMIN_URL.")

    admin_url = normalize_database_url(args.admin_url)
    expected = set(Base.metadata.tables)
    heads = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads()
    if len(heads) != 1:
        sys.exit(f"Expected a single migration head, found {heads}.")

    for number in range(1, args.rounds + 1):
        print(f"--- round {number}/{args.rounds}")
        try:
            with_throwaway_database(admin_url, lambda url: run_lifecycle(url, expected, heads[0]))
        except LifecycleError as exc:
            sys.exit(f"FAILED: {exc}")
    print(f"Migration lifecycle passed in {args.rounds} fresh database(s).")


if __name__ == "__main__":
    main()
