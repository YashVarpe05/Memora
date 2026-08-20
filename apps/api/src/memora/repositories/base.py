"""Per-owner data access.

CLAUDE.md, non-negotiable: every database read and write is scoped to a server-derived
user_id. This class is the only sanctioned way to build a query, and it cannot be
constructed without a user_id. Postgres RLS is the second layer; this is the first.

Never build a bare ``select(Model)`` in a service. Start from ``self.scoped()``.
"""

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from memora.db.base import Base


class BaseRepository[ModelT: Base]:
    """Base for all repositories. Subclasses set ``model``."""

    model: ClassVar[type[Base]]

    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        if user_id is None:
            raise ValueError(
                "BaseRepository requires a user_id. It must come from the verified "
                "access token — never from a request body or query parameter."
            )
        if not isinstance(user_id, UUID):
            raise TypeError(f"user_id must be a UUID, got {type(user_id).__name__}")
        self._session = session
        self._user_id = user_id

    @property
    def user_id(self) -> UUID:
        return self._user_id

    @property
    def session(self) -> AsyncSession:
        return self._session

    def scoped(self) -> Select[Any]:
        """The only correct starting point for a query in this codebase."""
        return select(self.model).where(self.model.user_id == self._user_id)  # type: ignore[attr-defined]

    async def get(self, entity_id: UUID) -> ModelT | None:
        stmt = self.scoped().where(self.model.id == entity_id)  # type: ignore[attr-defined]
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, entity: ModelT) -> ModelT:
        """Stamps ownership so a caller cannot insert a row owned by someone else."""
        entity.user_id = self._user_id  # type: ignore[attr-defined]
        self._session.add(entity)
        return entity
