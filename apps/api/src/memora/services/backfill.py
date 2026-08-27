"""Producing derived data for documents that predate the capability that makes it.

**The defect this exists for is general, not about CLIP.** A document ingested before a
capability existed could never acquire it: `find_by_hash` matches the content hash, the
upload route returns early, and every derivation step downstream is skipped. When CLIP
landed, 11 of 14 documents kept no image vector — the feature ran on a fifth of the corpus
and the measurement understated it badly.

Every future capability hits the same wall: a better OCR engine, a different embedder, a
third index. So this is a **backfill over missing artifacts**, not a patch to the dedup
branch. Adding a capability means adding a `Backfiller` here, and the documents that
predate it are covered by running the command again.

    uv run python -m memora.backfill --user <uuid>          # report what is missing
    uv run python -m memora.backfill --user <uuid> --apply  # produce it

Reports before it writes, and is idempotent: a document that already has an artifact is
skipped, so running it twice costs one query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from memora.db.models.image_embedding import ImageEmbedding
from memora.db.models.memory import Memory


@dataclass(frozen=True)
class Missing:
    artifact: str
    memory_id: UUID
    filename: str


class Backfiller(Protocol):
    """One derived artifact. Add a capability, add one of these."""

    artifact: str

    async def missing(self, session: AsyncSession, user_id: UUID) -> list[Missing]: ...

    async def produce(self, session: AsyncSession, user_id: UUID, item: Missing) -> bool:
        """True if produced. False means skipped for a reason worth reporting."""
        ...


class ImageEmbeddingBackfiller:
    """CLIP vectors for images that have none.

    Reads the original bytes back from blob storage rather than the database, because the
    picture is the input and only the blob has it.
    """

    artifact = "image_embedding"

    def __init__(self, embedder, blobs) -> None:
        self._embedder = embedder
        self._blobs = blobs

    async def missing(self, session: AsyncSession, user_id: UUID) -> list[Missing]:
        have = select(ImageEmbedding.memory_id).where(ImageEmbedding.user_id == user_id)
        rows = await session.execute(
            select(Memory.id, Memory.filename)
            .where(Memory.user_id == user_id)
            .where(Memory.source_type == "image")
            .where(Memory.id.not_in(have))
            .order_by(Memory.filename)
        )
        return [
            Missing(self.artifact, memory_id, filename) for memory_id, filename in rows
        ]

    async def produce(self, session: AsyncSession, user_id: UUID, item: Missing) -> bool:
        from memora.repositories.image_embedding import ImageEmbeddingRepository

        row = (
            await session.execute(
                select(Memory.content_hash).where(Memory.id == item.memory_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return False

        if not self._blobs.exists(user_id, row):
            # The row survives without its blob. Reported, not raised: one unreadable
            # file must not stop a backfill over hundreds.
            return False
        data = self._blobs.read(user_id, row)

        vector, model = await self._embedder.embed_image(data, item.filename)
        await ImageEmbeddingRepository(session, user_id).add(item.memory_id, vector, model)
        return True


async def find_missing(
    session: AsyncSession, user_id: UUID, backfillers: list[Backfiller]
) -> list[Missing]:
    out: list[Missing] = []
    for backfiller in backfillers:
        out.extend(await backfiller.missing(session, user_id))
    return out


async def run_backfill(
    session: AsyncSession,
    user_id: UUID,
    backfillers: list[Backfiller],
    apply: bool,
) -> tuple[list[Missing], list[Missing]]:
    """Returns (missing, produced). With apply=False nothing is written."""
    missing = await find_missing(session, user_id, backfillers)
    if not apply:
        return missing, []

    produced: list[Missing] = []
    by_artifact = {b.artifact: b for b in backfillers}
    for item in missing:
        if await by_artifact[item.artifact].produce(session, user_id, item):
            produced.append(item)
    return missing, produced
