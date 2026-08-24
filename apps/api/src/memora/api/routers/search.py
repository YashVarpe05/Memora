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
from memora.config import get_settings
from memora.repositories.chunk import ChunkRepository
from memora.services.embedding import Embedder, build_embedder
from memora.services.masking import mask_identifiers
from memora.services.query_signal import has_filterable_signal, why
from memora.services.query_understanding import (
    QueryFilters,
    QueryUnderstanding,
    build_query_understanding,
    passthrough,
)
from memora.services.retrieval import has_weak_evidence
from memora.services.search import Boosts, search_documents
from memora.services.stage1_health import describe, health

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
    # True when stage 1 was asked and could not answer. Reported rather than
    # swallowed: a total outage otherwise looks exactly like having no opinion.
    stage1_failed: bool = False
    stage1_failure_reason: str | None = None
    # A skip is a choice; a failure is a fault. Reported separately so quota
    # exhaustion can never hide inside a field that looks deliberate.
    stage1_skipped: bool = False
    stage1_skip_reason: str | None = None
    # A sentence for the user, present only when something is actually wrong. The
    # UI shows this; silent degradation to dense-only is the worst failure here.
    degraded_message: str | None = None


def get_embedder() -> Embedder:
    return build_embedder()


def get_query_understanding() -> QueryUnderstanding:
    settings = get_settings()
    inner = build_query_understanding()
    if not settings.stage1_cache:
        return inner

    from memora.services.stage1_cache import CachingQueryUnderstanding

    return CachingQueryUnderstanding(inner, model=settings.gemini_model)


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
    # A query with no source-type word, no sender and no date gets an empty extraction
    # anyway, so the call buys nothing. Twenty generate calls a day makes that worth
    # checking locally. See services/query_signal.py for what this cannot see.
    skipped = payload.stage1 and not has_filterable_signal(payload.query)
    if payload.stage1 and not skipped:
        started = time.perf_counter()
        filters = await stage_one.extract(payload.query)
        stage1_ms = int((time.perf_counter() - started) * 1000)
        health().record(failed=filters.failed, reason=filters.failure_reason)

    # The USER'S query is embedded, not stage 1's rewrite.
    #
    # Measured 2026-08-24 on q007. Stage 1 rewrote "the screenshot of that dashboard
    # with the forms on it" to "dashboard with the forms", dropping the word carrying
    # the match. The target fell from rank 2 (raw 0.547) to rank 4 (raw 0.509) - a
    # bigger loss than the +0.08 source-type boost could recover, so a correct filter
    # still produced a worse result.
    #
    # Stage 1 is trusted for filters and not for rewriting. semantic_query is still
    # returned in the response, because seeing what it would have done is useful.
    #
    # Masked like every other embedding: a description typed into a search box can
    # itself contain an identifier.
    query_vector = (await embedder.embed([mask_identifiers(payload.query)]))[0]

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
            stage1_failed=payload.stage1 and not skipped and filters.failed,
            stage1_failure_reason=(
                filters.failure_reason if filters.failed and not skipped else None
            ),
            stage1_skipped=skipped,
            stage1_skip_reason=why(payload.query) if skipped else None,
            degraded_message=describe(health().status()) if payload.stage1 else None,
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
        stage1_failed=payload.stage1 and not skipped and filters.failed,
        stage1_failure_reason=(
                filters.failure_reason if filters.failed and not skipped else None
            ),
        stage1_skipped=skipped,
        stage1_skip_reason=why(payload.query) if skipped else None,
        degraded_message=describe(health().status()) if payload.stage1 else None,
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
