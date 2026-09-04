"""Layer one: chunk hits in, ranked documents out.

PRODUCT.md architectural rule 1 - this module must never import generation. Finding a
file is retrieval and ranking; no part of a document should enter a model prompt just
because someone searched for it. `tests/test_no_llm_in_layer_one.py` asserts the import
graph rather than the behaviour, because a behaviour test keeps passing right up until
someone adds a "summarise the results" step.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from uuid import UUID

from memora.repositories.chunk import ChunkHit

if TYPE_CHECKING:
    from memora.repositories.image_embedding import ImageHit

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

# --- stage 1 filters, applied as boosts ------------------------------------------
#
# Matching a filter adds to a document's score; mismatching subtracts. Nothing is ever
# excluded.
#
# The reason is `mail.pdf` in the real corpus: a scanned print of a Gmail message, so its
# source_type is `pdf` while the query calls it "the mail". A strict `source_type: email`
# filter removes the correct answer and scores worse than no filtering at all. In a
# personal archive the format a thing arrives in rarely matches what it is, so a filter
# is evidence rather than truth.
#
# Additive rather than multiplicative because observed similarities sit in a narrow band
# (roughly 0.43 to 0.80), where a fixed increment is easier to reason about than a ratio.
FILTER_BONUS = 0.08


@dataclass(frozen=True)
class Boosts:
    """What stage 1 asks for. Every field optional; empty means no opinion."""

    source_types: tuple[str, ...] = ()
    sender: str | None = None
    after: object | None = None
    before: object | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.source_types or self.sender or self.after or self.before)


def boosted_score(hit: ChunkHit, boosts: Boosts) -> float:
    """A hit's score after stage 1's opinion is applied.

    Returned separately from `hit.similarity`, which stays raw. Refusal is decided on the
    raw score on purpose: whether there is genuinely good evidence should not change
    because stage 1 guessed a source type, and a threshold calibrated against boosted
    scores would drift every time the boost constant moved.
    """
    if boosts.is_empty:
        return hit.similarity

    score = hit.similarity

    if boosts.source_types:
        score += FILTER_BONUS if hit.source_type in boosts.source_types else -FILTER_BONUS

    if boosts.sender:
        sender = (hit.sender or "").lower()
        wanted = boosts.sender.lower()
        if sender and (wanted in sender or sender in wanted):
            score += FILTER_BONUS

    if (boosts.after or boosts.before) and hit.occurred_at is not None:
        within = True
        if boosts.after and hit.occurred_at < boosts.after:
            within = False
        if boosts.before and hit.occurred_at > boosts.before:
            within = False
        score += FILTER_BONUS if within else -FILTER_BONUS

    return score


@dataclass(frozen=True)
class DocumentResult:
    rank: int
    memory_id: UUID
    title: str
    filename: str
    source_type: str
    score: float
    # Before stage 1's boosts. Kept so a result can be explained.
    raw_score: float
    snippet: str
    # None when the document was found by its picture alone: a photo with no text
    # has no chunk to point at, which is the whole reason visual search exists.
    matched_chunk_id: UUID | None
    page: int | None
    byte_size: int
    has_thumbnail: bool
    # Set when the file is no longer on the device. The memory is still findable -
    # forgetting a document because it was tidied away is the failure this product
    # exists to fix - so the result carries the fact rather than being dropped.
    removed_at: object | None = None


@dataclass(frozen=True)
class SearchOutcome:
    results: list[DocumentResult]
    # Best unboosted similarity. Refusal is decided on this.
    raw_top_score: float
    # Observability for the bound above, so it is never a silent truncation.
    chunks_examined: int
    documents_in_window: int
    widenings: int
    exhausted: bool


def initial_window(limit: int) -> int:
    return max(limit, 1) * INITIAL_FANOUT


def group_by_document(
    hits: list[ChunkHit], boosts: Boosts | None = None
) -> list[tuple[ChunkHit, float]]:
    """One hit per document, paired with its boosted score.

    A document scores as its best chunk. For finding a document that is the right call -
    one strong match identifies it, while averaging dilutes a short decisive match with
    the rest of a long file. It is a knob the baseline will test, not a truth.
    """
    applied = boosts or Boosts()
    best: dict[UUID, tuple[ChunkHit, float]] = {}
    for hit in hits:
        score = boosted_score(hit, applied)
        current = best.get(hit.memory_id)
        if current is None or score > current[1]:
            best[hit.memory_id] = (hit, score)
    return sorted(best.values(), key=lambda pair: pair[1], reverse=True)


async def search_documents(
    fetch: Callable[[int], Awaitable[list[ChunkHit]]],
    limit: int,
    boosts: Boosts | None = None,
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
        grouped = group_by_document(hits, boosts)

        if len(grouped) >= limit or corpus_exhausted or window >= MAX_WINDOW:
            break

        window = min(window * 2, MAX_WINDOW)
        widenings += 1

    grouped = group_by_document(hits, boosts)
    # Refusal reads the RAW top similarity, never the boosted one - see boosted_score.
    raw_top = max((h.similarity for h in hits), default=0.0)
    return SearchOutcome(
        results=to_results(grouped[:limit]),
        raw_top_score=raw_top,
        chunks_examined=len(hits),
        documents_in_window=len(grouped),
        widenings=widenings,
        exhausted=corpus_exhausted,
    )


def to_results(scored: list[tuple[ChunkHit, float]]) -> list[DocumentResult]:
    return [
        DocumentResult(
            rank=index,
            memory_id=hit.memory_id,
            title=hit.title,
            filename=hit.filename,
            source_type=hit.source_type,
            score=round(score, 4),
            raw_score=round(hit.similarity, 4),
            # The stored chunk is already masked, so a result card cannot display an
            # identifier even when the source document contains one.
            snippet=hit.text[:SNIPPET_CHARS],
            matched_chunk_id=hit.chunk_id,
            page=hit.page,
            byte_size=hit.byte_size,
            has_thumbnail=hit.has_thumbnail,
            removed_at=hit.removed_at,
        )
        for index, (hit, score) in enumerate(scored, start=1)
    ]


def fuse_results(
    text_results: list[DocumentResult],
    image_hits: list[ImageHit],
    limit: int,
) -> list[DocumentResult]:
    """Merge the image list into the text list by rank, and renumber.

    Both inputs are already ranked. Only their ORDER crosses into fusion - the CLIP
    similarity never meets the text similarity, because there is no expression in which
    both appear. See services/fusion.py for why that matters.

    A document found only by CLIP has no chunk, so it has no snippet: it is a photo with
    no text, which is the entire reason this path exists. It carries an empty snippet and
    the UI says so, rather than showing a blank card.
    """
    from memora.services.fusion import reciprocal_rank_fusion

    by_id = {result.memory_id: result for result in text_results}
    image_by_id = {hit.memory_id: hit for hit in image_hits}

    fused = reciprocal_rank_fusion(
        text_order=[r.memory_id for r in text_results],
        image_order=[h.memory_id for h in image_hits],
    )

    merged: list[DocumentResult] = []
    for position, doc in enumerate(fused[:limit], start=1):
        existing = by_id.get(doc.memory_id)
        if existing is not None:
            merged.append(replace(existing, rank=position))
            continue

        hit = image_by_id[doc.memory_id]
        merged.append(
            DocumentResult(
                rank=position,
                memory_id=hit.memory_id,
                title=hit.title,
                filename=hit.filename,
                source_type=hit.source_type,
                # The RRF score, NOT a similarity. Deliberately not hit.similarity:
                # putting a CLIP 0.28 in the same column as a text 0.65 is exactly the
                # scale collision this design exists to prevent.
                score=round(doc.score, 6),
                raw_score=round(doc.score, 6),
                snippet="",
                matched_chunk_id=None,
                page=None,
                byte_size=hit.byte_size,
                has_thumbnail=hit.has_thumbnail,
                removed_at=hit.removed_at,
            )
        )
    return merged
