"""Layer one: POST /search.

Ranked documents, no generation call. This module must not import generation - see
the note in memora.services.search and the import-graph test.

POST rather than GET on purpose: "find my aadhaar card" is a personal description, and
a GET would put it in the URL, the browser history, and every access log in between.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from memora.api.deps import CurrentUserDep, DbDep
from memora.repositories.chunk import ChunkRepository
from memora.services.embedding import Embedder, build_embedder
from memora.services.masking import mask_identifiers
from memora.services.retrieval import has_weak_evidence
from memora.services.search import (
    distinct_documents_in_window,
    fetch_window,
    rank_documents,
)

router = APIRouter(tags=["search"])

MAX_LIMIT = 50


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=MAX_LIMIT)


class SearchResult(BaseModel):
    rank: int
    memory_id: str
    title: str
    filename: str
    source_type: str
    score: float
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
    # How many distinct documents the fetch window reached. Surfaced so the over-fetch
    # bound is observable rather than theoretical.
    documents_in_window: int


def get_embedder() -> Embedder:
    return build_embedder()


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    session: DbDep,
    user_id: CurrentUserDep,
    embedder: EmbedderDep,
) -> SearchResponse:
    # Masked like every other embedding: a description typed into the search box can
    # itself contain an identifier.
    query_vector = (await embedder.embed([mask_identifiers(payload.query)]))[0]

    chunks = ChunkRepository(session, user_id)
    hits = await chunks.search_hits(query_vector, fetch_window(payload.limit))

    if has_weak_evidence([h.similarity for h in hits]):
        return SearchResponse(
            refused=True,
            reason="no_evidence" if not hits else "weak_evidence",
            total=0,
            results=[],
            documents_in_window=0,
        )

    ranked = rank_documents(hits, payload.limit)

    return SearchResponse(
        refused=False,
        total=len(ranked),
        documents_in_window=distinct_documents_in_window(hits),
        results=[
            SearchResult(
                rank=r.rank,
                memory_id=str(r.memory_id),
                title=r.title,
                filename=r.filename,
                source_type=r.source_type,
                score=r.score,
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
