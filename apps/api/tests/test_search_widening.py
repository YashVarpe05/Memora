"""The fetch window widens instead of being a constant.

A fixed window is correct at exactly one corpus size. The corpus was 20 chunks and the
window was 50; one calendar export is 355 events, which turned that window into 14%
coverage from a single file. Raising the number buys one order of magnitude.

These drive `search_documents` with a stub fetcher, so the widening logic is tested
without a database and without pretending to know what pgvector will return.
"""

import uuid

from memora.repositories.chunk import ChunkHit
from memora.services.search import INITIAL_FANOUT, MAX_WINDOW, search_documents


def hit(memory_id: uuid.UUID, similarity: float) -> ChunkHit:
    return ChunkHit(
        chunk_id=uuid.uuid4(),
        memory_id=memory_id,
        text="text",
        contextual_prefix="",
        page=None,
        similarity=similarity,
        title="t",
        filename="f",
        source_type="pdf",
        byte_size=1,
        has_thumbnail=False,
    )


def corpus(chunks_per_document: list[int]) -> list[ChunkHit]:
    """Chunks ordered by descending similarity, document by document.

    Deliberately adversarial: every chunk of the first document outranks every chunk of
    the second. That is the crowding case a fixed window cannot survive.
    """
    hits: list[ChunkHit] = []
    score = 1.0
    for count in chunks_per_document:
        memory_id = uuid.uuid4()
        for _ in range(count):
            score -= 0.0001
            hits.append(hit(memory_id, score))
    return hits


def fetcher(hits: list[ChunkHit]):
    calls: list[int] = []

    async def fetch(n: int) -> list[ChunkHit]:
        calls.append(n)
        return hits[:n]

    return fetch, calls


async def test_one_crowding_document_does_not_hide_the_rest():
    """400 chunks of one document, then a second. A 50-chunk window would find one."""
    fetch, calls = fetcher(corpus([400, 3]))

    outcome = await search_documents(fetch, limit=2)

    assert len(outcome.results) == 2, "the second document was invisible"
    assert outcome.widenings > 0
    assert max(calls) > INITIAL_FANOUT * 2


async def test_no_widening_when_the_first_window_suffices():
    fetch, calls = fetcher(corpus([1, 1, 1]))

    outcome = await search_documents(fetch, limit=2)

    assert outcome.widenings == 0
    assert calls == [INITIAL_FANOUT * 2]


async def test_widening_stops_when_the_corpus_is_exhausted():
    """Fewer chunks than asked for means there is nothing left to miss."""
    fetch, _ = fetcher(corpus([2, 2]))

    outcome = await search_documents(fetch, limit=10)

    assert outcome.exhausted is True
    assert len(outcome.results) == 2


async def test_widening_stops_at_the_ceiling_and_says_so():
    """The bound is real, so it is reported rather than silently truncating."""
    fetch, calls = fetcher(corpus([MAX_WINDOW * 2, 5]))

    outcome = await search_documents(fetch, limit=5)

    assert max(calls) <= MAX_WINDOW
    assert outcome.exhausted is False, "hitting the ceiling is not the same as exhausting"
    assert outcome.chunks_examined <= MAX_WINDOW


async def test_a_document_appears_once_however_many_chunks_match():
    fetch, _ = fetcher(corpus([50]))

    outcome = await search_documents(fetch, limit=10)

    assert len(outcome.results) == 1


async def test_documents_are_ranked_by_their_best_chunk():
    strong, weak = uuid.uuid4(), uuid.uuid4()
    hits = [hit(weak, 0.9), hit(strong, 0.95), hit(weak, 0.1)]
    fetch, _ = fetcher(hits)

    outcome = await search_documents(fetch, limit=2)

    assert outcome.results[0].memory_id == strong
    assert outcome.results[0].score == 0.95
    assert outcome.results[1].score == 0.9


async def test_empty_corpus_returns_nothing_without_widening():
    fetch, calls = fetcher([])

    outcome = await search_documents(fetch, limit=10)

    assert outcome.results == []
    assert outcome.widenings == 0
    assert len(calls) == 1


async def test_ranks_are_one_based_and_contiguous():
    fetch, _ = fetcher(corpus([1, 1, 1, 1]))

    outcome = await search_documents(fetch, limit=3)

    assert [r.rank for r in outcome.results] == [1, 2, 3]
