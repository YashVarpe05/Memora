"""Shared FastAPI dependencies."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from memora.config import Settings, get_settings
from memora.db.session import get_session, scoped_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def current_user_id(request: Request, settings: SettingsDep) -> UUID:
    from memora.api.routers.pairing import get_store

    # Use the same overrideable store as the authentication gate.
    provider = request.app.dependency_overrides.get(get_store, get_store)
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else None
    identity = provider().identity(token)
    if identity:
        return identity
    if token or settings.is_production:
        raise HTTPException(401, "Connect this device to Memora again.")
    client = request.client.host if request.client else ""
    if not settings.require_pairing or client in ("127.0.0.1", "::1", "localhost"):
        return settings.dev_user_id
    raise HTTPException(401, "Connect this device to Memora first.")


CurrentUserDep = Annotated[UUID, Depends(current_user_id)]


async def get_db(
    user_id: CurrentUserDep,
) -> AsyncIterator[AsyncSession]:
    """The session every route should use. Carries app.user_id for RLS."""
    async for session in scoped_session(user_id):
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]
