"""Layer one: chunk hits in, ranked documents out.

PRODUCT.md architectural rule 1 - this module must never import generation. Finding a
file is retrieval and ranking; no part of a document should enter a model prompt just
because someone searched for it. `tests/test_no_llm_in_layer_one.py` asserts the import
graph rather than the behaviour, because a behaviour test keeps passing right up until
someone adds a "summarise the results" step.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from memora.repositories.chunk import ChunkHit

# How many chunks to fetch per requested document.
#
# The alternative, DISTINCT ON (memory_id), reads every chunk and defeats the HNSW
# index. Over-fetching keeps the index in play, at the cost of a real bound: a document
# whose only matching chunk falls outside the window is invisible. The worst case is a
# single document with many chunks crowding the window - so the number of documents
# reachable is at least (limit * FANOUT) / chunks_in_the_largest_document.
#
# MEASURED 2026-08-22 on the real corpus - 8 documents, 20 chunks, largest document
# 5 chunks, mean 2.5.
#
#   window at limit=10             50 chunks
#   whole corpus fetched while      total chunks <= 50, i.e. ~20 documents at 2.5 each
#   guaranteed reachable            50 / 5 = 10 documents, whatever the distribution
#   documents missable today        0 - the corpus is smaller than the window
#
# What this bounds is list completeness, not the top hit. A document with a strong match
# puts a chunk near the top of the window and is found regardless of corpus size; what
# degrades is the tail, where a document whose best chunk is mediocre falls out of the
# window entirely. So Recall@1 is robust here and Recall@5 is what erodes first.
#
# At a thousand documents the window covers about 2% of chunks. Raise the fanout, or
# move to a two-pass retrieve-then-group, before the corpus reaches that size. Carry
# this paragraph into BASELINE.md when the numbers are recorded.
SEARCH_FANOUT = 5

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


def fetch_window(limit: int) -> int:
    return max(limit, 1) * SEARCH_FANOUT


def rank_documents(hits: list[ChunkHit], limit: int) -> list[DocumentResult]:
    """Collapse chunk hits into ranked documents.

    A document scores as its best chunk. For finding a document that is the right
    call - one strong match identifies it, while averaging dilutes a short decisive
    match with the rest of a long file. It is a knob the baseline will test, not a
    truth.
    """
    best: dict[UUID, ChunkHit] = {}
    for hit in hits:
        current = best.get(hit.memory_id)
        if current is None or hit.similarity > current.similarity:
            best[hit.memory_id] = hit

    ordered = sorted(best.values(), key=lambda h: h.similarity, reverse=True)[:limit]

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
        for index, hit in enumerate(ordered, start=1)
    ]


def distinct_documents_in_window(hits: list[ChunkHit]) -> int:
    """How many documents the fetch window actually reached.

    Reported so the over-fetch bound is an observed number rather than a caveat.
    """
    return len({hit.memory_id for hit in hits})
