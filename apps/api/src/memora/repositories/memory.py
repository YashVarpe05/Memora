"""Memory queries. Every one starts from scoped()."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import update as sql_update

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
        document_type: str | None = None,
        sender: str | None = None,
        occurred_at: object | None = None,
        device_path: str | None = None,
    ) -> Memory:
        memory = Memory(
            source_type=source_type,
            title=title,
            filename=filename,
            content_hash=content_hash,
            byte_size=byte_size,
            mime_type=mime_type,
            has_thumbnail=has_thumbnail,
            document_type=document_type,
            sender=sender,
            occurred_at=occurred_at,
            device_path=device_path,
        )
        self.add(memory)
        await self.session.flush()
        return memory

    async def document_types(self) -> set[str | None]:
        """Which document types this user actually holds.

        Scoped, like everything here. A global query would let one user's corpus decide
        whether another user's search is refused - which leaks the existence of a
        document without ever showing it.
        """
        result = await self.session.execute(
            self.scoped().with_only_columns(Memory.document_type).distinct()
        )
        return set(result.scalars().all())

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

    async def device_paths(self) -> dict[str, UUID]:
        """Every device-discovered memory this user still has on the phone.

        Returns path -> id so reconciliation can diff in Python. A `NOT IN` with a few
        thousand bind parameters is the alternative, and it is both slower and capped by
        the driver's parameter limit.
        """
        rows = await self.session.execute(
            self.scoped()
            .with_only_columns(Memory.device_path, Memory.id)
            .where(Memory.device_path.is_not(None))
        )
        return {path: memory_id for path, memory_id in rows}

    async def mark_removed(self, memory_ids: list[UUID], at: datetime) -> int:
        """The file is gone from the device; the memory is not.

        Idempotent by design - re-running a scan must not keep rewriting timestamps, or
        "removed on 14 March" would silently become "removed on 20 March" and the one fact
        the result promises the user would be wrong.
        """
        if not memory_ids:
            return 0
        result = await self.session.execute(
            sql_update(Memory)
            .where(Memory.user_id == self.user_id)
            .where(Memory.id.in_(memory_ids))
            .where(Memory.removed_at.is_(None))
            .values(removed_at=at)
        )
        return result.rowcount or 0

    async def mark_present(self, memory_ids: list[UUID]) -> int:
        """A file that came back - restored from a backup, or un-deleted.

        Without this a file could only ever be marked gone once, and the record would
        keep claiming a removal that is no longer true.
        """
        if not memory_ids:
            return 0
        result = await self.session.execute(
            sql_update(Memory)
            .where(Memory.user_id == self.user_id)
            .where(Memory.id.in_(memory_ids))
            .where(Memory.removed_at.is_not(None))
            .values(removed_at=None)
        )
        return result.rowcount or 0
