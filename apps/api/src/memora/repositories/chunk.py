"""Chunk queries, including dense retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from memora.db.models.chunk import Chunk
from memora.db.models.memory import Memory
from memora.repositories.base import BaseRepository


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    similarity: float


@dataclass(frozen=True)
class ChunkHit:
    """One matching chunk, carrying enough of its document to build a result card."""

    chunk_id: UUID
    memory_id: UUID
    text: str
    contextual_prefix: str
    page: int | None
    similarity: float

    title: str
    filename: str
    source_type: str
    byte_size: int
    has_thumbnail: bool
    # Null unless a full device scan stopped finding the file. Carried through
    # retrieval so a result can say the file is gone rather than fail to open.
    removed_at: object | None = None
    sender: str | None = None
    occurred_at: object | None = None


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

        Layer two uses this. Layer one uses search_hits, which carries the document.
        """
        distance = Chunk.embedding.cosine_distance(embedding)
        stmt = self.scoped().add_columns(distance.label("distance")).order_by(distance).limit(k)
        rows = await self.session.execute(stmt)
        return [ScoredChunk(chunk=row[0], similarity=1.0 - float(row[1])) for row in rows]

    async def search_hits(self, embedding: list[float], k: int) -> list[ChunkHit]:
        """Top-k chunks with their document, in one query.

        Joined rather than looked up per chunk: ranking needs every hit's document, and
        an N+1 here would run once per result on every search.
        """
        distance = Chunk.embedding.cosine_distance(embedding)
        stmt = (
            self.scoped()
            .join(Memory, Memory.id == Chunk.memory_id)
            .add_columns(
                distance.label("distance"),
                Memory.title,
                Memory.filename,
                Memory.source_type,
                Memory.byte_size,
                Memory.has_thumbnail,
                Memory.removed_at,
                Memory.sender,
                Chunk.occurred_at.label("chunk_at"),
            )
            .order_by(distance)
            .limit(k)
        )
        rows = await self.session.execute(stmt)
        return [
            ChunkHit(
                chunk_id=chunk.id,
                memory_id=chunk.memory_id,
                text=chunk.text,
                contextual_prefix=chunk.contextual_prefix,
                page=chunk.page,
                similarity=1.0 - float(distance_value),
                title=title,
                filename=filename,
                source_type=source_type,
                byte_size=byte_size,
                has_thumbnail=has_thumbnail,
                removed_at=removed_at,
                sender=sender,
                occurred_at=chunk_at,
            )
            for (
                chunk,
                distance_value,
                title,
                filename,
                source_type,
                byte_size,
                has_thumbnail,
                removed_at,
                sender,
                chunk_at,
            ) in rows
        ]

    async def count_for_memory(self, memory_id: UUID) -> int:
        stmt = self.scoped().where(Chunk.memory_id == memory_id)
        result = await self.session.execute(stmt)
        return len(result.scalars().all())
