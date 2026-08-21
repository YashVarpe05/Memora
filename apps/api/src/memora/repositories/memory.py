"""Memory queries. Every one starts from scoped()."""

from __future__ import annotations

from memora.db.models.memory import Memory
from memora.repositories.base import BaseRepository


class MemoryRepository(BaseRepository[Memory]):
    model = Memory

    async def create(self, *, source_type: str, title: str, filename: str) -> Memory:
        memory = Memory(source_type=source_type, title=title, filename=filename)
        self.add(memory)
        await self.session.flush()
        return memory
