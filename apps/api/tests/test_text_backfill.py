"""Model provenance, resumable semantic coverage, and per-device isolation."""

import uuid

import pytest
from sqlalchemy import text

from memora.db.models.chunk import Chunk
from memora.repositories.chunk import ChunkRepository
from memora.repositories.memory import MemoryRepository
from memora.services.embedding_backfill import backfill_batch

from support import FakeEmbedder


class TargetEmbedder(FakeEmbedder):
    fingerprint = "test:model-b:768:unit:v1"


async def add_chunks(db, user_id, *, count=3, model="test:model-a:768:unit:v1", vector=True):
    memory = await MemoryRepository(db, user_id).create(
        source_type="pdf",
        title="Synthetic records",
        filename="234.pdf",
    )
    chunks = [
        Chunk(
            ordinal=i,
            text=f"Aadhaar synthetic record {i}",
            contextual_prefix="Synthetic title",
            token_count=5,
            page=i + 1,
            embedding=FakeEmbedder._vector(f"record {i}") if vector else None,
            embedding_model=model,
        )
        for i in range(count)
    ]
    await ChunkRepository(db, user_id).add_many(memory.id, chunks)
    return chunks


async def test_same_dimensions_different_models_never_mix(db, test_user_id):
    chunks = await add_chunks(db, test_user_id)
    chunks[1].embedding_model = TargetEmbedder.fingerprint
    chunks[2].embedding_model = None  # Old unlabelled vector is not assumed compatible.
    await db.flush()
    repo = ChunkRepository(db, test_user_id)
    query = FakeEmbedder._vector("record")
    assert [h.chunk_id for h in await repo.search_hits(query, 10, TargetEmbedder.fingerprint)] == [
        chunks[1].id
    ]
    assert [h.chunk.id for h in await repo.search_dense(query, 10, TargetEmbedder.fingerprint)] == [
        chunks[1].id
    ]
    assert [h.chunk_id for h in await repo.search_hits(query, 10)] == [chunks[2].id]
    assert len(await repo.search_lexical("Aadhaar", 10, "aadhaar")) == 3


async def test_backfill_resumes_skips_completed_and_preserves_text(db, test_user_id):
    chunks = await add_chunks(db, test_user_id, vector=False, model=None)
    original = [(c.id, c.text, c.page) for c in chunks]
    embedder = TargetEmbedder()
    repo = ChunkRepository(db, test_user_id)
    assert await repo.pending_embedding_count(embedder.fingerprint) == 3
    assert await backfill_batch(db, test_user_id, embedder, batch_size=1) == 1
    assert await repo.pending_embedding_count(embedder.fingerprint) == 2
    # A newly constructed worker resumes from durable row provenance, not a cursor.
    restarted = TargetEmbedder()
    assert await backfill_batch(db, test_user_id, restarted, batch_size=10) == 2
    assert await backfill_batch(db, test_user_id, restarted, batch_size=10) == 0
    assert len(restarted.calls[0]) == 2
    assert [(c.id, c.text, c.page) for c in chunks] == original
    assert all(c.embedding_model == embedder.fingerprint for c in chunks)
    assert await repo.pending_embedding_count(embedder.fingerprint) == 0


async def test_failed_batch_is_retryable_without_losing_old_vectors(db, test_user_id):
    chunks = await add_chunks(db, test_user_id)
    previous = [c.embedding_model for c in chunks]

    class Interrupted(TargetEmbedder):
        async def embed(self, texts):
            raise ConnectionError("interrupted")

    with pytest.raises(ConnectionError):
        await backfill_batch(db, test_user_id, Interrupted())
    assert [c.embedding_model for c in chunks] == previous
    assert await backfill_batch(db, test_user_id, TargetEmbedder()) == 3


@pytest.mark.parametrize("vectors", [[], [[1.0]], [[float("nan")] * 768]])
async def test_invalid_provider_response_cannot_mark_chunks_complete(db, test_user_id, vectors):
    chunks = await add_chunks(db, test_user_id, count=1)

    class Invalid(TargetEmbedder):
        async def embed(self, texts):
            return vectors

    with pytest.raises(ValueError, match="invalid batch"):
        await backfill_batch(db, test_user_id, Invalid())
    assert chunks[0].embedding_model != TargetEmbedder.fingerprint


async def test_backfill_re_masks_stored_content_and_context(db, test_user_id):
    chunks = await add_chunks(db, test_user_id, count=1)
    chunks[0].text = "Aadhaar ABCDE1234F synthetic"
    chunks[0].contextual_prefix = "Owner ABCDE1234F"
    await db.flush()
    embedder = TargetEmbedder()
    await backfill_batch(db, test_user_id, embedder)
    assert "ABCDE1234F" not in embedder.calls[0][0]
    assert "[PAN_NUMBER]" in embedder.calls[0][0]


async def test_backfill_cannot_read_or_update_another_device(db, test_user_id):
    chunks = await add_chunks(db, test_user_id)
    stranger = uuid.uuid4()
    await db.execute(text("SELECT set_config('app.user_id', :id, true)"), {"id": str(stranger)})
    embedder = TargetEmbedder()
    assert await backfill_batch(db, stranger, embedder) == 0
    assert await ChunkRepository(db, stranger).pending_embedding_count(embedder.fingerprint) == 0
    assert (await db.execute(text("SELECT * FROM chunks"))).all() == []
    assert embedder.calls == []
    await db.execute(text("SELECT set_config('app.user_id', :id, true)"), {"id": str(test_user_id)})
    assert all(c.embedding_model != embedder.fingerprint for c in chunks)


async def test_removed_documents_do_not_consume_backfill_work(db, test_user_id):
    from datetime import UTC, datetime

    chunks = await add_chunks(db, test_user_id)
    memory = await MemoryRepository(db, test_user_id).get(chunks[0].memory_id)
    memory.removed_at = datetime.now(UTC)
    await db.flush()
    assert await backfill_batch(db, test_user_id, TargetEmbedder()) == 0


async def test_unfingerprinted_embedder_cannot_relabel_legacy_vectors(db, test_user_id):
    with pytest.raises(ValueError, match="fingerprint"):
        await backfill_batch(db, test_user_id, FakeEmbedder())


async def test_committed_batch_survives_next_batch_interruption(db, test_user_id):
    chunks = await add_chunks(db, test_user_id, vector=False, model=None)
    memory_id = chunks[0].memory_id
    target = TargetEmbedder()
    await db.commit()

    async def scope():
        await db.execute(
            text("SELECT set_config('app.user_id', :id, true)"), {"id": str(test_user_id)}
        )

    class Interrupted(TargetEmbedder):
        async def embed(self, texts):
            raise ConnectionError("interrupted")

    try:
        await scope()
        assert await backfill_batch(db, test_user_id, target, batch_size=1) == 1
        await db.commit()
        await scope()
        with pytest.raises(ConnectionError):
            await backfill_batch(db, test_user_id, Interrupted(), batch_size=1)
        await db.rollback()
        db.expunge_all()
        await scope()
        repo = ChunkRepository(db, test_user_id)
        assert await repo.pending_embedding_count(target.fingerprint) == 2
        assert await backfill_batch(db, test_user_id, TargetEmbedder()) == 2
        await db.commit()
        await scope()
        assert await repo.pending_embedding_count(target.fingerprint) == 0
    finally:
        await db.rollback()
        await scope()
        await MemoryRepository(db, test_user_id).delete(memory_id)
        await db.commit()


async def test_concurrent_backfills_skip_locked_rows(db, test_user_id):
    from sqlalchemy.ext.asyncio import AsyncSession

    chunks = await add_chunks(db, test_user_id, vector=False, model=None)
    memory_id = chunks[0].memory_id
    await db.commit()
    try:
        await db.execute(
            text("SELECT set_config('app.user_id', :id, true)"), {"id": str(test_user_id)}
        )
        first = await ChunkRepository(db, test_user_id).next_embedding_batch(
            TargetEmbedder.fingerprint,
            1,
        )
        async with AsyncSession(bind=db.bind) as concurrent:
            await concurrent.execute(
                text("SELECT set_config('app.user_id', :id, true)"), {"id": str(test_user_id)}
            )
            others = await ChunkRepository(concurrent, test_user_id).next_embedding_batch(
                TargetEmbedder.fingerprint,
                10,
            )
            assert len(first) == 1 and len(others) == 2
            assert first[0].id not in {row.id for row in others}
            await concurrent.rollback()
    finally:
        await db.rollback()
        await db.execute(
            text("SELECT set_config('app.user_id', :id, true)"), {"id": str(test_user_id)}
        )
        await MemoryRepository(db, test_user_id).delete(memory_id)
        await db.commit()
