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
from memora.repositories.image_embedding import ImageEmbeddingRepository, ImageHit
from memora.repositories.memory import MemoryRepository
from memora.services.document_type import classify, should_refuse
from memora.services.embedding import Embedder, build_embedder
from memora.services.image_embedding import (
    ImageEmbedder,
    ImageEmbeddingUnavailable,
    build_image_embedder,
)
from memora.services.masking import mask_identifiers
from memora.services.query_signal import has_filterable_signal, why
from memora.services.query_understanding import (
    QueryFilters,
    QueryUnderstanding,
    build_query_understanding,
    passthrough,
)
from memora.services.retrieval import has_weak_evidence, has_weak_image_evidence
from memora.services.search import Boosts, fuse_results, search_documents
from memora.services.stage1_health import describe, health

router = APIRouter(tags=["search"])

MAX_LIMIT = 50


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=MAX_LIMIT)
    # The ablation switch. Off runs the dense-only path BASELINE.md recorded, so
    # both arms can be measured in one session against one corpus.
    stage1: bool = True
    # The second ablation, one level in: run stage 1 on EVERY query, including the ones
    # the signal heuristic would skip. This is the falsifier for keeping the skip - it
    # is the only way to see what a skipped row would have got. Costs a call per skipped
    # query, so it is off by default and belongs to the harness, not to real use.
    stage1_skip: bool = True
    # Visual search. Off makes the ablation arm measurable against the text-only
    # numbers every report before this one recorded.
    images: bool = True


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
    matched_chunk_id: str | None
    page: int | None
    byte_size: int
    thumbnail_url: str | None
    file_url: str
    # ISO timestamp when the file left the device, or null. The card renders
    # "removed from device" rather than offering a file that cannot open.
    removed_at: str | None = None


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
    """Stage 1, local by default.

    Local is not a fallback for when the quota runs out - it is the configuration the
    product ships in. Hosted is reachable with STAGE1_PROVIDER=gemini and exists so the
    ablation can report both, not because the system depends on it.
    """
    settings = get_settings()
    if settings.stage1_provider == "local":
        from memora.services.local_query_understanding import (
            build_local_query_understanding,
        )

        # Not cached: the cache exists to conserve a metered quota, and there is none.
        return build_local_query_understanding(settings.local_stage1_model)

    inner = build_query_understanding()
    if not settings.stage1_cache:
        return inner

    from memora.services.stage1_cache import CachingQueryUnderstanding

    return CachingQueryUnderstanding(inner, model=settings.gemini_model)


def get_image_embedder() -> ImageEmbedder:
    return build_image_embedder()


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
ImageEmbedderDep = Annotated[ImageEmbedder, Depends(get_image_embedder)]
StageOneDep = Annotated[QueryUnderstanding, Depends(get_query_understanding)]


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    session: DbDep,
    user_id: CurrentUserDep,
    embedder: EmbedderDep,
    stage_one: StageOneDep,
    image_embedder: ImageEmbedderDep,
) -> SearchResponse:
    filters: QueryFilters = passthrough(payload.query)
    stage1_ms: int | None = None
    # A query with no source-type word, no sender and no date gets an empty extraction
    # anyway, so the call buys nothing. Twenty generate calls a day makes that worth
    # checking locally. See services/query_signal.py for what this cannot see.
    skipped = (
        payload.stage1
        and payload.stage1_skip
        and not has_filterable_signal(payload.query)
    )
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
        document_type=filters.document_type,
        sender=filters.sender,
        after=filters.after,
        before=filters.before,
    )

    chunks = ChunkRepository(session, user_id)
    outcome = await search_documents(
        lambda n: chunks.search_hits(query_vector, n), payload.limit, boosts
    )
    ranked = outcome.results

    # The image list, fused in by RANK. Some documents have no text at all - a photo of
    # people yields an empty OCR string - so the text list cannot contain them at any
    # quality. Their vector is CLIP's, on a scale where 0.28 is strong, and it is never
    # compared with the text similarities. See services/fusion.py.
    image_hits: list[ImageHit] = []
    if payload.images:
        try:
            clip_vector, _ = await image_embedder.embed_text(payload.query)
            image_hits = await ImageEmbeddingRepository(session, user_id).search(
                clip_vector, payload.limit * 2
            )
        except ImageEmbeddingUnavailable:
            # Degrade to text-only. Visual search being down must not stop a search that
            # the text index can answer perfectly well.
            image_hits = []

    # The image index contributes ONLY documents the text index did not find.
    #
    # This is structural and needs no constant. CLIP exists to find documents the text
    # index CANNOT find - a photo with no text has no chunk, so it can never appear in
    # the text list at any quality. A document already in the text list is ranked by its
    # text, and adding a visual bonus on top is precisely what broke ranking.
    #
    # Measured 2026-08-26. Fusing the raw image list dropped Recall@1 from 0.895 to
    # 0.316; filtering to hits above the evidence threshold recovered it only to 0.632.
    # RRF rewards a document appearing in BOTH lists, which is sound only when both lists
    # are SELECTIVE - and CLIP is not, it ranks everything. The WhatsApp screenshots carry
    # OCR text and image vectors, so they appeared in both lists for every query and
    # collected an agreement bonus a text-only PDF could never earn. Images topped twelve
    # queries they had nothing to do with.
    #
    # The evidence threshold still applies as a floor, so a visually-irrelevant document
    # cannot enter on a near-zero score. But the gate that matters is this one, and it is
    # a property of the corpus rather than a tuned number.
    text_found = {result.memory_id for result in outcome.results}
    image_evidence = [
        hit
        for hit in image_hits
        if hit.memory_id not in text_found
        and not has_weak_image_evidence([hit.similarity])
    ]
    if image_evidence:
        # Stage 1 is asked first and usually declines: qwen2.5:3b returns
        # document_type=None for "my college ID card" even though `id_card` is in the
        # schema enum, because the field is not in `required` and a 3B model omits
        # what it may omit. Measured, not assumed - the tie-break shipped inert on
        # that assumption once already.
        #
        # So the query is classified by the SAME vocabulary that classifies documents.
        # A corpus file is typed from its filename; a query is typed from its words;
        # one table, both sides, no model in the loop. Deterministic and free.
        #
        # Ranking only. `filters.document_type` still drives refusal on its own, so
        # this cannot talk the system into or out of refusing - refusal is measured
        # separately and must not move because a ranking signal improved.
        wanted_type = filters.document_type or classify(text=payload.query)
        ranked = fuse_results(
            ranked, image_evidence, payload.limit, wanted_type=wanted_type
        )

    # Raw similarity, not boosted - a filter guess must not talk the system out of
    # refusing. See boosted_score in services/search.py.
    # Refusal asks whether EITHER index found something, on its own scale. Asking only
    # the text index refuses every photo that has no text - which is precisely the
    # document visual search exists to find, so the feature would be unreachable.
    # Refusal by document-type agreement, decided BEFORE the score.
    #
    # PHASE3.md: no threshold separates absent from present. q021 "my college fee receipt"
    # scores 0.647 - above NINE documents that are the correct answer to their own query -
    # because the calendar genuinely contains events about college and fees. Absence is not
    # low similarity.
    #
    # This tests what the person actually asked for. They named a receipt; nothing in the
    # corpus IS a receipt; refuse regardless of how well the words match. Scoped to this
    # user, so another owner's documents cannot decide whether this one is refused.
    type_mismatch = False
    if filters.document_type:
        held = await MemoryRepository(session, user_id).document_types()
        type_mismatch = should_refuse(filters.document_type, held)

    text_weak = has_weak_evidence([outcome.raw_top_score] if outcome.results else [])
    image_weak = not image_evidence
    if type_mismatch or (text_weak and image_weak):
        return SearchResponse(
            refused=True,
            reason=(
                f"no_{filters.document_type}_in_corpus"
                if type_mismatch
                else ("no_evidence" if not ranked else "weak_evidence")
            ),
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
                matched_chunk_id=str(r.matched_chunk_id) if r.matched_chunk_id else None,
                page=r.page,
                byte_size=r.byte_size,
                thumbnail_url=(
                    f"/memories/{r.memory_id}/thumbnail" if r.has_thumbnail else None
                ),
                file_url=f"/memories/{r.memory_id}/file",
                removed_at=r.removed_at.isoformat() if r.removed_at else None,
            )
            for r in ranked
        ],
    )
