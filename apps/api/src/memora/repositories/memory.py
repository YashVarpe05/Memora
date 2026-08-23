"""Memory queries. Every one starts from scoped()."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete as sql_delete

from memora.db.models.chunk import Chunk
from memora.db.models.memory import Memory
from memora.repositories.base import BaseRepository


class MemoryRepository(BaseRepository[Memory]):
    model = Memory

    async def create(
        self,
        *,
        source_type: str,
        title: str,
        filename: str,
        content_hash: str = "",
        byte_size: int = 0,
        mime_type: str = "",
        has_thumbnail: bool = False,
    ) -> Memory:
        memory = Memory(
            source_type=source_type,
            title=title,
            filename=filename,
            content_hash=content_hash,
            byte_size=byte_size,
            mime_type=mime_type,
            has_thumbnail=has_thumbnail,
        )
        self.add(memory)
        await self.session.flush()
        return memory

    async def find_by_hash(self, content_hash: str) -> Memory | None:
        """Deduplication lookup, scoped to this owner.

        Scoped, not global. A global lookup would let one user learn that another holds
        a file simply by observing their own upload deduplicate.
        """
        result = await self.session.execute(
            self.scoped().where(Memory.content_hash == content_hash)
        )
        return result.scalars().first()

    async def delete(self, entity_id: UUID) -> Memory | None:
        """Remove the memory and its chunks. Returns the row so the caller can drop
        the blob - PRODUCT.md requires erasure to be demonstrable, and a row deleted
        while its file survives on disk is not erasure.

        Chunks are removed explicitly rather than relying on the FK cascade, because
        the cascade runs as the table owner while the API runs under RLS.
        """
        memory = await self.get(entity_id)
        if memory is None:
            return None

        await self.session.execute(
            sql_delete(Chunk).where(
                Chunk.memory_id == memory.id, Chunk.user_id == self.user_id
            )
        )
        await self.session.delete(memory)
        await self.session.flush()
        return memory
