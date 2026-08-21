"""RLS actually isolates - proven with raw SQL, not through the repository.

CLAUDE.md rule 2: the repository already filters WHERE user_id = ..., so a test routed
through it returns zero rows for user B whether or not a policy exists. These issue
SELECT with no WHERE clause and let the policy be the only thing standing between the
query and the rows.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from memora.config import get_settings

USER_A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
USER_B = uuid.UUID("00000000-0000-4000-8000-00000000000b")


@pytest_asyncio.fixture
async def engine():
    """Connects as the runtime role - non-superuser, so policies actually bind."""
    eng = create_async_engine(get_settings().database_url)
    try:
        conn = await eng.connect()
        await conn.close()
    except Exception as exc:  # noqa: BLE001
        await eng.dispose()
        pytest.skip(f"Postgres not reachable: {type(exc).__name__}")
    try:
        yield eng
    finally:
        await eng.dispose()


async def _insert_memory_as(conn, user: uuid.UUID) -> uuid.UUID:
    memory_id = uuid.uuid4()
    await conn.execute(
        text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user)}
    )
    await conn.execute(
        text(
            "INSERT INTO memories (id, user_id, source_type, title, filename) "
            "VALUES (:id, :uid, 'pdf', 'secret', 'secret.pdf')"
        ),
        {"id": memory_id, "uid": str(user)},
    )
    return memory_id


async def test_user_b_cannot_see_user_a_rows(engine):
    async with engine.begin() as conn:
        await _insert_memory_as(conn, USER_A)

        # Same transaction, switch identity, unfiltered read.
        await conn.execute(
            text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(USER_B)}
        )
        rows = (await conn.execute(text("SELECT * FROM memories"))).fetchall()

        assert rows == [], "user B read user A's rows - the policy is not enforcing"
        await conn.rollback()


async def test_owner_sees_their_own_rows(engine):
    """The mirror of the above. A policy that blocks everyone proves nothing."""
    async with engine.begin() as conn:
        await _insert_memory_as(conn, USER_A)
        rows = (await conn.execute(text("SELECT * FROM memories"))).fetchall()

        assert len(rows) == 1
        await conn.rollback()


async def test_never_set_session_var_fails_closed(engine):
    """Two-arg current_setting returns NULL when unset, and user_id = NULL matches nothing."""
    async with engine.begin() as seed:
        await _insert_memory_as(seed, USER_A)
        await seed.commit()

    try:
        async with engine.begin() as conn:
            # app.user_id was never set on this connection.
            rows = (await conn.execute(text("SELECT * FROM memories"))).fetchall()
            assert rows == [], "unset session var opened the table instead of closing it"
    finally:
        async with engine.begin() as cleanup:
            await cleanup.execute(
                text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(USER_A)}
            )
            await cleanup.execute(text("DELETE FROM memories"))


async def test_empty_session_var_fails_closed(engine):
    """SET but empty must yield zero rows, not a cast error.

    Without NULLIF in the policy, ''::uuid raises - which surfaces as a 500 rather
    than a closed door, and a 500 is a much worse way to find out.
    """
    async with engine.begin() as conn:
        await _insert_memory_as(conn, USER_A)

        await conn.execute(text("SELECT set_config('app.user_id', '', true)"))
        rows = (await conn.execute(text("SELECT * FROM memories"))).fetchall()

        assert rows == []
        await conn.rollback()


async def test_user_b_cannot_insert_rows_owned_by_user_a(engine):
    """WITH CHECK: an owner cannot write a row attributed to someone else."""
    from sqlalchemy.exc import DBAPIError

    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(USER_B)}
        )
        with pytest.raises(DBAPIError):
            await conn.execute(
                text(
                    "INSERT INTO memories (id, user_id, source_type, title, filename) "
                    "VALUES (:id, :uid, 'pdf', 'forged', 'f.pdf')"
                ),
                {"id": uuid.uuid4(), "uid": str(USER_A)},
            )
        await conn.rollback()
