"""Chunk queries, including dense retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from memora.db.models.chunk import Chunk
from memora.repositories.base import BaseRepository


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    similarity: float


class ChunkRepository(BaseRepository[Chunk]):
    model = Chunk

    async def add_many(self, memory_id: UUID, chunks: list[Chunk]) -> list[Chunk]:
        for chunk in chunks:
            chunk.memory_id = memory_id
            self.add(chunk)
        await self.session.flush()
        return chunks

    async def search_dense(self, embedding: list[float], k: int) -> list[ScoredChunk]:
        """Plain cosine nearest-neighbour inside this user's rows.

        Phase 1 only. Phase 3 replaces this with filters + hybrid + RRF, and the
        ablation needs this number recorded before that happens.
        """
        distance = Chunk.embedding.cosine_distance(embedding)
        stmt = self.scoped().add_columns(distance.label("distance")).order_by(distance).limit(k)
        rows = await self.session.execute(stmt)
        return [ScoredChunk(chunk=row[0], similarity=1.0 - float(row[1])) for row in rows]

    async def count_for_memory(self, memory_id: UUID) -> int:
        stmt = self.scoped().where(Chunk.memory_id == memory_id)
        result = await self.session.execute(stmt)
        return len(result.scalars().all())
