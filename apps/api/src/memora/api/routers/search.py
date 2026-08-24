"""Layer one: POST /search.

Ranked documents, no generation call. This module must not import generation - see
the note in memora.services.search and the import-graph test.

POST rather than GET on purpose: "find my aadhaar card" is a personal description, and
a GET would put it in the URL, the browser history, and every access log in between.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from memora.api.deps import CurrentUserDep, DbDep
from memora.repositories.chunk import ChunkRepository
from memora.services.embedding import Embedder, build_embedder
from memora.services.masking import mask_identifiers
from memora.services.query_understanding import (
    QueryFilters,
    QueryUnderstanding,
    build_query_understanding,
    passthrough,
)
from memora.services.retrieval import has_weak_evidence
from memora.services.search import Boosts, search_documents

router = APIRouter(tags=["search"])

MAX_LIMIT = 50


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=MAX_LIMIT)
    # The ablation switch. Off runs the dense-only path BASELINE.md recorded, so
    # both arms can be measured in one session against one corpus.
    stage1: bool = True


class SearchResult(BaseModel):
    rank: int
    memory_id: str
    title: str
    filename: str
    source_type: str
    score: float
    # Before stage 1's boosts, so a ranking can be explained rather than trusted.
    raw_score: float
    snippet: str
    matched_chunk_id: str
    page: int | None
    byte_size: int
    thumbnail_url: str | None
    file_url: str


class SearchResponse(BaseModel):
    refused: bool
    reason: str | None = None
    total: int
    results: list[SearchResult]
    # Retrieval bound, surfaced rather than hidden. The window widens until enough
    # documents surface; these say how much work that took and whether the corpus was
    # fully covered.
    chunks_examined: int
    documents_in_window: int
    widenings: int
    corpus_exhausted: bool
    # What stage 1 extracted, so a result can be explained rather than trusted.
    filters: dict | None = None
    stage1_ms: int | None = None


def get_embedder() -> Embedder:
    return build_embedder()


def get_query_understanding() -> QueryUnderstanding:
    return build_query_understanding()


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
StageOneDep = Annotated[QueryUnderstanding, Depends(get_query_understanding)]


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    session: DbDep,
    user_id: CurrentUserDep,
    embedder: EmbedderDep,
    stage_one: StageOneDep,
) -> SearchResponse:
    filters: QueryFilters = passthrough(payload.query)
    stage1_ms: int | None = None
    if payload.stage1:
        started = time.perf_counter()
        filters = await stage_one.extract(payload.query)
        stage1_ms = int((time.perf_counter() - started) * 1000)

    # Masked like every other embedding: a description typed into the search box can
    # itself contain an identifier.
    query_vector = (await embedder.embed([mask_identifiers(filters.semantic_query)]))[0]

    boosts = Boosts(
        source_types=filters.source_types,
        sender=filters.sender,
        after=filters.after,
        before=filters.before,
    )

    chunks = ChunkRepository(session, user_id)
    outcome = await search_documents(
        lambda n: chunks.search_hits(query_vector, n), payload.limit, boosts
    )
    ranked = outcome.results

    # Raw similarity, not boosted - a filter guess must not talk the system out of
    # refusing. See boosted_score in services/search.py.
    if has_weak_evidence([outcome.raw_top_score] if ranked else []):
        return SearchResponse(
            refused=True,
            reason="no_evidence" if not ranked else "weak_evidence",
            total=0,
            results=[],
            chunks_examined=outcome.chunks_examined,
            documents_in_window=outcome.documents_in_window,
            widenings=outcome.widenings,
            corpus_exhausted=outcome.exhausted,
            filters=filters.raw or None,
            stage1_ms=stage1_ms,
        )

    return SearchResponse(
        refused=False,
        total=len(ranked),
        chunks_examined=outcome.chunks_examined,
        documents_in_window=outcome.documents_in_window,
        widenings=outcome.widenings,
        corpus_exhausted=outcome.exhausted,
        filters=filters.raw or None,
        stage1_ms=stage1_ms,
        results=[
            SearchResult(
                rank=r.rank,
                memory_id=str(r.memory_id),
                title=r.title,
                filename=r.filename,
                source_type=r.source_type,
                score=r.score,
                raw_score=r.raw_score,
                snippet=r.snippet,
                matched_chunk_id=str(r.matched_chunk_id),
                page=r.page,
                byte_size=r.byte_size,
                thumbnail_url=(
                    f"/memories/{r.memory_id}/thumbnail" if r.has_thumbnail else None
                ),
                file_url=f"/memories/{r.memory_id}/file",
            )
            for r in ranked
        ],
    )
