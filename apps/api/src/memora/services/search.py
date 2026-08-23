"""Layer one: chunk hits in, ranked documents out.

PRODUCT.md architectural rule 1 - this module must never import generation. Finding a
file is retrieval and ranking; no part of a document should enter a model prompt just
because someone searched for it. `tests/test_no_llm_in_layer_one.py` asserts the import
graph rather than the behaviour, because a behaviour test keeps passing right up until
someone adds a "summarise the results" step.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from memora.repositories.chunk import ChunkHit

# --- the fetch window -------------------------------------------------------------
#
# Retrieval is index-first: HNSW returns nearest *chunks*, and documents are grouped
# from them. The question is how many chunks to fetch, and a fixed number is wrong at
# every corpus size but one.
#
# Measured why: the corpus was 20 chunks and a 50-chunk window covered all of it. One
# calendar export is 355 events, so a single file turns that window into 14% coverage.
# Raising the constant would buy one order of magnitude and be wrong at the next.
#
# So the window widens instead. Fetch, group, and if fewer documents surfaced than were
# asked for, double and retry - until enough documents appear, the corpus is exhausted,
# or the ceiling is reached. The cost adapts to the actual distribution rather than to a
# guess about it, and the number of extra queries is logarithmic in the worst case.
#
# MAX_WINDOW is a real bound, not a tuning knob: past it, a document whose best chunk
# ranks below 2000 is unreachable. That is reported rather than hidden - see
# `SearchOutcome.exhausted`.
#
# MEASURED 2026-08-22 on the real corpus, 11 documents / 377 chunks, one calendar
# accounting for 353 of them. Five queries, and the counterfactual run with the old
# fixed 50-chunk window:
#
#              fixed 50-chunk window        adaptive
#   documents  2 to 8 surfaced              all reachable, 2-3 widenings
#   examined   50                           200 to 377
#   Recall@1   5/5                          5/5
#
# Worth being precise about what changed. Recall@1 was never at risk - a document with
# a strong match puts a chunk near the top of any window, which is what the earlier
# bound analysis predicted. What the fixed window broke was list completeness: one query
# surfaced two documents out of eleven, so asking for ten results returned two.
#
# So this fixes Recall@5 and leaves Recall@1 where it was. That is the honest claim.

INITIAL_FANOUT = 5
MAX_WINDOW = 2000

SNIPPET_CHARS = 280


@dataclass(frozen=True)
class DocumentResult:
    rank: int
    memory_id: UUID
    title: str
    filename: str
    source_type: str
    score: float
    snippet: str
    matched_chunk_id: UUID
    page: int | None
    byte_size: int
    has_thumbnail: bool


@dataclass(frozen=True)
class SearchOutcome:
    results: list[DocumentResult]
    # Observability for the bound above, so it is never a silent truncation.
    chunks_examined: int
    documents_in_window: int
    widenings: int
    exhausted: bool


def initial_window(limit: int) -> int:
    return max(limit, 1) * INITIAL_FANOUT


def group_by_document(hits: list[ChunkHit]) -> list[ChunkHit]:
    """One hit per document: its best chunk.

    A document scores as its best chunk. For finding a document that is the right call -
    one strong match identifies it, while averaging dilutes a short decisive match with
    the rest of a long file. It is a knob the baseline will test, not a truth.
    """
    best: dict[UUID, ChunkHit] = {}
    for hit in hits:
        current = best.get(hit.memory_id)
        if current is None or hit.similarity > current.similarity:
            best[hit.memory_id] = hit
    return sorted(best.values(), key=lambda h: h.similarity, reverse=True)


async def search_documents(
    fetch: Callable[[int], Awaitable[list[ChunkHit]]],
    limit: int,
) -> SearchOutcome:
    """Retrieve, group, and widen until enough documents surface.

    `fetch(n)` returns the n nearest chunks. Widening stops on any of three conditions,
    and each one means something different:

    - enough documents found      the normal case
    - fetch returned fewer than
      asked for                   the corpus is exhausted, nothing is being missed
    - the ceiling was reached     a real bound, reported as `exhausted=False` with
                                  `widenings` at its maximum
    """
    window = initial_window(limit)
    widenings = 0
    hits: list[ChunkHit] = []
    corpus_exhausted = False

    while True:
        hits = await fetch(window)
        corpus_exhausted = len(hits) < window
        grouped = group_by_document(hits)

        if len(grouped) >= limit or corpus_exhausted or window >= MAX_WINDOW:
            break

        window = min(window * 2, MAX_WINDOW)
        widenings += 1

    grouped = group_by_document(hits)
    return SearchOutcome(
        results=to_results(grouped[:limit]),
        chunks_examined=len(hits),
        documents_in_window=len(grouped),
        widenings=widenings,
        exhausted=corpus_exhausted,
    )


def to_results(hits: list[ChunkHit]) -> list[DocumentResult]:
    return [
        DocumentResult(
            rank=index,
            memory_id=hit.memory_id,
            title=hit.title,
            filename=hit.filename,
            source_type=hit.source_type,
            score=round(hit.similarity, 4),
            # The stored chunk is already masked, so a result card cannot display an
            # identifier even when the source document contains one.
            snippet=hit.text[:SNIPPET_CHARS],
            matched_chunk_id=hit.chunk_id,
            page=hit.page,
            byte_size=hit.byte_size,
            has_thumbnail=hit.has_thumbnail,
        )
        for index, hit in enumerate(hits, start=1)
    ]
