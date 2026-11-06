"""Resumable semantic indexing. Existing text remains searchable throughout."""

from __future__ import annotations

import math
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from memora.db.models.chunk import EMBEDDING_DIMS
from memora.repositories.chunk import ChunkRepository
from memora.services.embedding import Embedder, embedding_fingerprint
from memora.services.masking import mask_all


async def backfill_batch(
    session: AsyncSession, user_id: UUID, embedder: Embedder, *, batch_size: int = 16
) -> int:
    """Update one locked batch; the caller commits or rolls back the whole batch.

    A restart finds rows missing this exact fingerprint. No text, file, or previously
    successful batch is deleted. SKIP LOCKED prevents concurrent workers duplicating
    a batch. Failed embedding leaves the old vectors and provenance unchanged.
    """
    model_id = embedding_fingerprint(embedder)
    if not model_id:
        raise ValueError("Backfill requires an explicit embedding model fingerprint")
    repo = ChunkRepository(session, user_id)
    rows = await repo.next_embedding_batch(model_id, batch_size)
    if not rows:
        return 0
    vectors = await embedder.embed(
        mask_all(
            [
                f"{row.contextual_prefix}\n\n{row.text}" if row.contextual_prefix else row.text
                for row in rows
            ]
        )
    )
    if len(vectors) != len(rows) or any(
        len(vector) != EMBEDDING_DIMS
        or not all(math.isfinite(value) for value in vector)
        or not any(vector)
        for vector in vectors
    ):
        raise ValueError("Embedding provider returned invalid batch vectors")
    # Validate the entire response before mutating any ORM row.
    for row, vector in zip(rows, vectors, strict=True):
        row.embedding = vector
        row.embedding_model = model_id
    await session.flush()
    return len(rows)
