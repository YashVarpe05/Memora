"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from memora.config import Settings, get_settings
from memora.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

# Phase 2 adds CurrentUserDep here: decodes the Bearer access token and returns a
# verified user_id. Repositories take that value — never a client-supplied id.
