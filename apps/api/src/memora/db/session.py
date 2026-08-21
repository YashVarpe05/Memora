"""Async engine and session lifecycle."""

from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from memora.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Yields a session and always closes it."""
    async with get_sessionmaker()() as session:
        yield session


async def scoped_session(user_id: UUID) -> AsyncIterator[AsyncSession]:
    """A transaction with app.user_id set for its lifetime.

    set_config(..., true) is SET LOCAL: it dies with the transaction. A session-level
    SET would survive on a pooled connection, and the next request to pick up that
    connection would inherit this user's identity until it overwrote it.

    set_config is used rather than literal SET because it is a function and takes a
    bind parameter - SET is a utility statement and would need string interpolation.
    """
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user_id)}
        )
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
