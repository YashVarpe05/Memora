"""RLS is only real if the connection identity cannot bypass it.

Superusers ignore RLS unconditionally, and FORCE ROW LEVEL SECURITY does not change
that. An API connected as the owner-superuser leaves every policy inert while every
policy test still passes. These assert the precondition, before any policy exists.

Skipped when Postgres is unreachable, so `pytest` stays green without docker up.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from memora.config import get_settings


@pytest.fixture
async def runtime_connection():
    """Connects exactly as the API does at runtime."""
    engine = create_async_engine(get_settings().database_url)
    try:
        conn = await engine.connect()
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"Postgres not reachable: {type(exc).__name__}")
    try:
        yield conn
    finally:
        await conn.close()
        await engine.dispose()


async def test_runtime_role_cannot_bypass_rls(runtime_connection):
    user, is_super, can_bypass = (
        await runtime_connection.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )
        )
    ).one()
    assert not is_super, f"API connects as superuser '{user}' - every RLS policy is inert"
    assert not can_bypass, f"role '{user}' has BYPASSRLS - every RLS policy is inert"


async def test_runtime_role_owns_no_tables(runtime_connection):
    """Table owners bypass their own RLS unless FORCE is set. Owning nothing is safer."""
    owned = (
        await runtime_connection.execute(
            text(
                "SELECT count(*) FROM pg_tables "
                "WHERE schemaname = 'public' AND tableowner = current_user"
            )
        )
    ).scalar_one()
    assert owned == 0, f"runtime role owns {owned} table(s) in public"


def test_runtime_and_migration_roles_are_different():
    """No database needed: pointing both at one role is the whole failure mode."""
    settings = get_settings()
    assert settings.database_url != settings.migration_database_url
