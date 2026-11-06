"""Chunk queries, including dense retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_

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
    lexical_score: float = 0.0
    removed_at: object | None = None
    # What kind of document this is. Stage 1 already extracts the type a query asks
    # for; until now nothing compared the two when ranking.
    document_type: str | None = None
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

    async def search_dense(
        self, embedding: list[float], k: int, model_id: str | None = None
    ) -> list[ScoredChunk]:
        """Plain cosine nearest-neighbour inside this user's rows.

        Layer two uses this. Layer one uses search_hits, which carries the document.
        """
        distance = Chunk.embedding.cosine_distance(embedding)
        stmt = (
            self.scoped()
            .where(Chunk.embedding.is_not(None), Chunk.embedding_model == model_id)
            .add_columns(distance.label("distance"))
            .order_by(distance)
            .limit(k)
        )
        rows = await self.session.execute(stmt)
        return [ScoredChunk(chunk=row[0], similarity=1.0 - float(row[1])) for row in rows]

    async def search_hits(
        self, embedding: list[float], k: int, model_id: str | None = None
    ) -> list[ChunkHit]:
        """Top-k chunks with their document, in one query.

        Joined rather than looked up per chunk: ranking needs every hit's document, and
        an N+1 here would run once per result on every search.
        """
        distance = Chunk.embedding.cosine_distance(embedding)
        stmt = (
            self.scoped()
            .join(Memory, Memory.id == Chunk.memory_id)
            .where(Chunk.embedding.is_not(None), Chunk.embedding_model == model_id)
            .add_columns(
                distance.label("distance"),
                Memory.title,
                Memory.filename,
                Memory.source_type,
                Memory.byte_size,
                Memory.has_thumbnail,
                Memory.removed_at,
                Memory.document_type,
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
                document_type=document_type,
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
                document_type,
                sender,
                chunk_at,
            ) in rows
        ]

    def _pending_embedding_query(self, model_id: str):
        if not model_id:
            raise ValueError("Backfill requires an explicit embedding model fingerprint")
        return (
            self.scoped()
            .join(Memory, Memory.id == Chunk.memory_id)
            .where(
                Memory.removed_at.is_(None),
                Chunk.text != "",
                or_(Chunk.embedding.is_(None), Chunk.embedding_model.is_distinct_from(model_id)),
            )
        )

    async def pending_embedding_count(self, model_id: str) -> int:
        stmt = self._pending_embedding_query(model_id).with_only_columns(func.count(Chunk.id))
        return int((await self.session.execute(stmt)).scalar_one())

    async def next_embedding_batch(self, model_id: str, limit: int = 16) -> list[Chunk]:
        if not 1 <= limit <= 128:
            raise ValueError("Embedding batch size must be between 1 and 128")
        stmt = (
            self._pending_embedding_query(model_id)
            .order_by(Chunk.memory_id, Chunk.ordinal, Chunk.id)
            .limit(limit)
            .with_for_update(of=Chunk, skip_locked=True)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_for_memory(self, memory_id: UUID) -> int:
        stmt = self.scoped().where(Chunk.memory_id == memory_id)
        result = await self.session.execute(stmt)
        return len(result.scalars().all())

    async def search_lexical(self, query: str, k: int, wanted_type: str | None) -> list[ChunkHit]:
        from memora.services.lexical import bm25

        # Fetch only searchable text and display metadata, never 768-dimensional vectors.
        rows = (
            await self.session.execute(
                self.scoped()
                .join(Memory, Memory.id == Chunk.memory_id)
                .with_only_columns(
                    Chunk.id,
                    Chunk.memory_id,
                    Chunk.text,
                    Chunk.contextual_prefix,
                    Chunk.page,
                    Memory.title,
                    Memory.filename,
                    Memory.source_type,
                    Memory.byte_size,
                    Memory.has_thumbnail,
                    Memory.removed_at,
                    Memory.document_type,
                    Memory.sender,
                    Chunk.occurred_at,
                )
            )
        ).all()
        scores = bm25(query, [r.text + " " + r.filename for r in rows])
        hits = []
        for row, score in zip(rows, scores, strict=True):
            type_match = wanted_type is not None and row.document_type == wanted_type
            if score <= 0 and not type_match:
                continue
            hits.append(
                (
                    type_match,
                    score,
                    ChunkHit(
                        chunk_id=row.id,
                        memory_id=row.memory_id,
                        text=row.text,
                        contextual_prefix=row.contextual_prefix,
                        page=row.page,
                        similarity=0.0,
                        lexical_score=score,
                        title=row.title,
                        filename=row.filename,
                        source_type=row.source_type,
                        byte_size=row.byte_size,
                        has_thumbnail=row.has_thumbnail,
                        removed_at=row.removed_at,
                        document_type=row.document_type,
                        sender=row.sender,
                        occurred_at=row.occurred_at,
                    ),
                )
            )
        hits.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [hit for _, _, hit in hits[:k]]
