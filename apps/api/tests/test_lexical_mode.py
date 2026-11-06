"""The keyless web trial indexes real text without fabricated model vectors."""

import uuid

import pytest

from memora.api.routers import search, uploads
from memora.config import get_settings
from memora.db.models.chunk import Chunk
from memora.repositories.chunk import ChunkRepository
from memora.services.image_embedding import build_image_embedder

from support import make_pdf


@pytest.fixture
def lexical(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_provider", "lexical")
    monkeypatch.setattr(settings, "gemini_api_key", None)
    return settings


def test_lexical_mode_initializes_no_embedding_clients(lexical):
    assert uploads.get_embedder() is None
    assert search.get_embedder() is None
    assert build_image_embedder() is None


def test_hosted_default_still_requires_a_key(lexical, monkeypatch):
    monkeypatch.setattr(lexical, "embedding_provider", "gemini")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        uploads.get_embedder()


async def test_real_keyless_ingest_search_and_dense_exclusion(api, app, db, test_user_id, lexical):
    for dependency in (
        uploads.get_embedder, uploads.get_image_embedder,
        search.get_embedder, search.get_image_embedder, search.get_query_understanding,
    ):
        app.dependency_overrides.pop(dependency, None)

    uploaded = await api.post(
        "/uploads", files={"file": (
            "2344646563rt.pdf",
            make_pdf(["Aadhaar card\nUnique Identification Authority\nABCDE1234F"]),
            "application/pdf",
        )},
    )
    assert uploaded.status_code == 201, uploaded.text
    mid = uuid.UUID(uploaded.json()["memory_id"])
    repo = ChunkRepository(db, test_user_id)
    chunks = (await db.execute(repo.scoped().where(Chunk.memory_id == mid))).scalars().all()
    assert chunks and all(chunk.embedding is None for chunk in chunks)
    assert all("ABCDE1234F" not in chunk.text for chunk in chunks)
    assert await repo.search_hits([1.0] + [0.0] * 767, 5) == []
    assert await repo.search_dense([1.0] + [0.0] * 767, 5) == []

    response = await api.post("/search", json={"query": "mera adhaar"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["results"][0]["memory_id"] == str(mid)
    assert body["results"][0]["page"] == 1
    assert "Meaning-based search is unavailable" in body["degraded_message"]


async def test_readiness_discloses_lexical_mode(api, lexical):
    response = await api.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["search_mode"] == "lexical"
    assert "disabled" in response.json()["degraded_message"]
