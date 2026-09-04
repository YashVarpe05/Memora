"""Image-vector queries. Scoped, like every repository here."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from memora.db.models.image_embedding import ImageEmbedding
from memora.db.models.memory import Memory
from memora.repositories.base import BaseRepository


@dataclass(frozen=True)
class ImageHit:
    """One matching image, carrying enough of its document to build a result card.

    Deliberately the same shape as ChunkHit where they overlap, so fusion can treat both
    as ranked lists of documents without either side knowing about the other's scale.
    """

    memory_id: UUID
    similarity: float

    title: str
    filename: str
    source_type: str
    byte_size: int
    has_thumbnail: bool
    # Same field as ChunkHit carries. The shapes must not diverge: fusion builds result
    # cards from either, so a field on one and not the other crashes only on the path
    # where an image outranks every chunk - the rarest path, found last.
    removed_at: object | None = None
    document_type: str | None = None
    sender: str | None = None


class ImageEmbeddingRepository(BaseRepository[ImageEmbedding]):
    model = ImageEmbedding

    async def add(self, memory_id: UUID, embedding: list[float], model: str) -> ImageEmbedding:
        row = ImageEmbedding(memory_id=memory_id, embedding=embedding, model=model)
        super().add(row)
        await self.session.flush()
        return row

    async def search(self, embedding: list[float], k: int) -> list[ImageHit]:
        """Nearest images to a CLIP text vector, inside this user's rows.

        The similarity returned here is on CLIP's scale, where ~0.28 is a strong match.
        It must never be compared against text similarities, which sit near 0.6. Callers
        fuse by RANK, not by score.
        """
        distance = ImageEmbedding.embedding.cosine_distance(embedding)
        stmt = (
            self.scoped()
            .join(Memory, Memory.id == ImageEmbedding.memory_id)
            .add_columns(
                distance.label("distance"),
                Memory.title,
                Memory.filename,
                Memory.source_type,
                Memory.byte_size,
                Memory.has_thumbnail,
                Memory.sender,
                Memory.removed_at,
                Memory.document_type,
            )
            .order_by(distance)
            .limit(k)
        )
        rows = await self.session.execute(stmt)
        return [
            ImageHit(
                memory_id=row[0].memory_id,
                similarity=1.0 - float(row[1]),
                title=row[2],
                filename=row[3],
                source_type=row[4],
                byte_size=row[5],
                has_thumbnail=row[6],
                sender=row[7],
                removed_at=row[8],
                document_type=row[9],
            )
            for row in rows
        ]

    async def count(self) -> int:
        result = await self.session.execute(self.scoped())
        return len(result.scalars().all())
