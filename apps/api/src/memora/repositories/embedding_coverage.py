"""Per-device semantic index coverage, never inferred from provider configuration."""

from sqlalchemy import and_, case, false, func

from memora.db.models.chunk import Chunk
from memora.db.models.memory import Memory
from memora.repositories.chunk import ChunkRepository
from memora.repositories.memory import MemoryRepository


class EmbeddingCoverageRepository(MemoryRepository):
    async def counts(self, model_id: str | None) -> dict[str, int]:
        compatible = and_(Chunk.embedding.is_not(None), Chunk.embedding_model == model_id)
        if model_id is None:
            compatible = false()
        chunks = (
            ChunkRepository(self.session, self.user_id).scoped()
            .with_only_columns(
                Chunk.memory_id,
                func.count(Chunk.id).label("total"),
                func.count(case((compatible, 1))).label("indexed"),
            )
            .group_by(Chunk.memory_id).subquery()
        )
        result = await self.session.execute(
            self.scoped()
            .outerjoin(chunks, chunks.c.memory_id == Memory.id)
            .where(Memory.removed_at.is_(None))
            .with_only_columns(
                func.count(Memory.id).label("available_documents"),
                func.count(chunks.c.memory_id).label("text_documents"),
                func.count(case((chunks.c.indexed == chunks.c.total, 1)))
                .label("semantic_documents"),
            )
        )
        counts = dict(result.mappings().one())
        counts["pending_documents"] = counts["text_documents"] - counts["semantic_documents"]
        counts["no_text_documents"] = counts["available_documents"] - counts["text_documents"]
        return counts
