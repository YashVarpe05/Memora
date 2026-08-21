"""Shared FastAPI dependencies."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from memora.config import Settings, get_settings
from memora.db.session import get_session, scoped_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]



async def current_user_id(settings: SettingsDep) -> UUID:
    """The server-derived identity.

    Phase 1 has no auth, so this returns the dev UUID from settings. Phase 2 swaps the
    body for "decode the Bearer token" and nothing downstream changes - which is the
    point of routing it through a dependency now rather than passing a literal around.

    It is never read from a request body, query string, or header.
    """
    return settings.dev_user_id


CurrentUserDep = Annotated[UUID, Depends(current_user_id)]


async def get_db(
    user_id: CurrentUserDep,
) -> AsyncIterator[AsyncSession]:
    """The session every route should use. Carries app.user_id for RLS."""
    async for session in scoped_session(user_id):
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]
