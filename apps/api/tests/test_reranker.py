"""Reranking changes the order of results and nothing else."""

import uuid

from memora.api.routers import search
from memora.config import Settings
from memora.services.reranker import PASSAGE_CHARS, passage_for, rerank_results
from memora.services.search import DocumentResult


def _result(rank: int, title: str, passage: str = "") -> DocumentResult:
    return DocumentResult(
        rank=rank,
        memory_id=uuid.uuid4(),
        title=title,
        filename=title,
        source_type="pdf",
        score=1.0 / rank,
        raw_score=0.8,
        snippet=passage[:50],
        matched_chunk_id=None,
        page=1,
        byte_size=1,
        has_thumbnail=False,
        passage=passage,
    )


class KeywordReranker:
    """Scores a passage by how many query words it contains."""

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []

    def score(self, query: str, passages: list[str]) -> list[float]:
        self.calls.append((query, passages))
        words = query.lower().split()
        return [float(sum(w in p.lower() for w in words)) for p in passages]


async def test_the_best_passage_moves_to_rank_one_and_ranks_are_renumbered():
    results = [_result(1, "a", "fee receipt"), _result(2, "b", "train ticket pune delhi")]
    reranked = await rerank_results(KeywordReranker(), "train ticket", results, top_n=20)
    assert [r.title for r in reranked] == ["b", "a"]
    assert [r.rank for r in reranked] == [1, 2]


async def test_only_the_top_n_are_reranked_and_the_tail_keeps_its_order():
    results = [_result(i, f"d{i}", "x") for i in range(1, 6)]
    results[3] = _result(4, "d4", "train ticket")  # beyond top_n, so it must not jump
    fake = KeywordReranker()
    reranked = await rerank_results(fake, "train ticket", results, top_n=2)
    assert len(fake.calls[0][1]) == 2
    assert [r.title for r in reranked][2:] == ["d3", "d4", "d5"]


async def test_ties_and_single_results_keep_their_order():
    results = [_result(1, "a", "same"), _result(2, "b", "same")]
    assert [r.title for r in await rerank_results(KeywordReranker(), "q", results, 20)] == [
        "a",
        "b",
    ]
    one = [_result(1, "a", "x")]
    fake = KeywordReranker()
    assert await rerank_results(fake, "q", one, 20) == one and fake.calls == []


def test_the_reranker_is_off_by_default_and_reads_a_bounded_passage():
    assert Settings().reranker == "off"
    assert search.get_reranker() is None
    assert len(passage_for("context", "x" * 5000)) == PASSAGE_CHARS


async def test_search_reorders_with_an_injected_reranker_and_never_refuses_on_it(
    api, app, db, test_user_id
):
    for name, body in {
        "fee.txt": "Fee receipt. College of Engineering. Semester 5 tuition paid.",
        "ticket.txt": "Indian Railways e-ticket. Train Pune to Delhi. Departure 18:40.",
    }.items():
        assert (
            await api.post("/uploads", files={"file": (name, body.encode(), "text/plain")})
        ).status_code == 201
    app.dependency_overrides[search.get_reranker] = lambda: KeywordReranker()
    try:
        response = await api.post("/search", json={"query": "train ticket delhi"})
    finally:
        app.dependency_overrides.pop(search.get_reranker, None)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False
    assert body["results"][0]["filename"] == "ticket.txt"
