"""Semantic progress is scoped, model-specific, and requires every text chunk."""

import uuid
from datetime import UTC, datetime

from memora.api.routers.search import get_embedder
from memora.config import get_settings
from memora.db.models.chunk import Chunk
from memora.repositories.chunk import ChunkRepository
from memora.repositories.embedding_coverage import EmbeddingCoverageRepository
from memora.repositories.memory import MemoryRepository

from support import FakeEmbedder

MODEL = "test:coverage:model-v1"
VECTOR = [1.0] + [0.0] * 767


async def document(db, owner, name, models, removed=False):
    memory = await MemoryRepository(db, owner).create(
        source_type="pdf", title=name, filename=f"{name}.pdf"
    )
    if removed:
        memory.removed_at = datetime.now(UTC)
    chunks = [
        Chunk(text=f"Synthetic {name} {i}", token_count=4, ordinal=i,
              embedding=VECTOR if model else None, embedding_model=model)
        for i, model in enumerate(models)
    ]
    await ChunkRepository(db, owner).add_many(memory.id, chunks)
    return memory


async def test_coverage_requires_all_current_model_chunks_and_excludes_removed(db, test_user_id):
    await document(db, test_user_id, "complete", [MODEL, MODEL])
    await document(db, test_user_id, "partial", [MODEL, None])
    await document(db, test_user_id, "old-model", ["test:old-model"])
    await document(db, test_user_id, "no-text", [])
    await document(db, test_user_id, "removed", [MODEL], removed=True)
    assert await EmbeddingCoverageRepository(db, test_user_id).counts(MODEL) == {
        "available_documents": 4, "text_documents": 3, "semantic_documents": 1,
        "pending_documents": 2, "no_text_documents": 1,
    }
    # Unlabelled/disabled providers may never claim a legacy vector is compatible.
    assert (await EmbeddingCoverageRepository(db, test_user_id).counts(None))[
        "semantic_documents"
    ] == 0
    assert all(v == 0 for v in (
        await EmbeddingCoverageRepository(db, uuid.uuid4()).counts(MODEL)
    ).values())


async def test_coverage_endpoint_distinguishes_model_configuration_from_readiness(
    api, app, db, test_user_id, monkeypatch
):
    class ConfiguredEmbedder(FakeEmbedder):
        fingerprint = MODEL
        ready = False

    monkeypatch.setattr(get_settings(), "embedding_provider", "local")
    app.dependency_overrides[get_embedder] = ConfiguredEmbedder
    await document(db, test_user_id, "waiting", [None])
    response = await api.get("/index/coverage")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is True and body["model_ready"] is False
    assert body["semantic_documents"] == 0 and body["pending_documents"] == 1
    assert body["provider"] == "local"


async def test_disabled_meaning_search_never_claims_indexed_legacy_vectors(
    api, app, db, test_user_id, monkeypatch
):
    monkeypatch.setattr(get_settings(), "embedding_provider", "lexical")
    app.dependency_overrides[get_embedder] = lambda: None
    await document(db, test_user_id, "legacy", [MODEL])
    body = (await api.get("/index/coverage")).json()
    assert body["configured"] is False
    assert body["model_ready"] is None
    assert body["semantic_documents"] == 0
