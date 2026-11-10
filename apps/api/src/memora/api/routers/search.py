"""Layer one: POST /search.

Ranked documents, no generation call. This module must not import generation - see
the note in memora.services.search and the import-graph test.

POST rather than GET on purpose: "find my aadhaar card" is a personal description, and
a GET would put it in the URL, the browser history, and every access log in between.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from memora.api.deps import CurrentUserDep, DbDep
from memora.config import get_settings
from memora.repositories.chunk import ChunkRepository
from memora.repositories.image_embedding import ImageEmbeddingRepository, ImageHit
from memora.repositories.memory import MemoryRepository
from memora.services.document_type import classify, should_refuse
from memora.services.embedding import (
    Embedder,
    build_embedder,
    embed_query,
    embedding_fingerprint,
)
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
from memora.services.retrieval import (
    MIN_SIMILARITY_UNCALIBRATED,
    has_weak_evidence,
    has_weak_image_evidence,
    is_uncertain,
)
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
    hybrid: bool = True


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
    document_type: str | None = None
    document_label: str | None = None
    match_explanation: str = "Matched document contents"
    uncertain: bool = False


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


def get_embedder() -> Embedder | None:
    settings = get_settings()
    if settings.embedding_provider == "lexical":
        return None
    if settings.embedding_provider == "local" or settings.gemini_api_key:
        return build_embedder()
    return None


def get_query_understanding() -> QueryUnderstanding:
    """Rules by default; optional model providers remain available for evaluation."""
    settings = get_settings()
    if settings.stage1_provider == "rules":
        # No model at all. The fourth ablation arm, and the one that decides whether
        # the on-device build needs an LLM - see prompts/rules-stage1.md.
        from memora.services.rules_query_understanding import RulesQueryUnderstanding

        return RulesQueryUnderstanding()

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


def get_image_embedder() -> ImageEmbedder | None:
    return build_image_embedder()


EmbedderDep = Annotated[Embedder | None, Depends(get_embedder)]
ImageEmbedderDep = Annotated[ImageEmbedder | None, Depends(get_image_embedder)]
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
        and classify(text=payload.query) is None
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
    query_vector = None
    embedding_degraded = None
    try:
        if embedder is None:
            raise RuntimeError("Embedding is not configured")
        async with asyncio.timeout(5):
            query_vector = await embed_query(embedder, mask_identifiers(payload.query))
    except Exception:
        embedding_degraded = (
            "Meaning-based search is unavailable. Showing word and document-type matches."
        )

    wanted_type = filters.document_type or classify(text=payload.query)
    if wanted_type and filters.document_type is None:
        filters = replace(filters, document_type=wanted_type)

    boosts = Boosts(
        source_types=filters.source_types,
        document_type=filters.document_type,
        sender=filters.sender,
        after=filters.after,
        before=filters.before,
    )

    chunks = ChunkRepository(session, user_id)

    async def dense_window(n: int):
        return (await chunks.search_hits(query_vector, n, model_id=embedding_fingerprint(embedder))
                if query_vector is not None else [])

    outcome = await search_documents(dense_window, payload.limit, boosts)
    ranked = outcome.results
    lexical_ids: set = set()
    if payload.hybrid:
        from memora.services.lexical import excerpt
        from memora.services.search import DocumentResult, boosted_score

        lexical_hits = await chunks.search_lexical(payload.query, 2000, wanted_type)
        lexical_hits.sort(
            key=lambda h: (
                bool(wanted_type and h.document_type == wanted_type),
                h.lexical_score + boosted_score(h, boosts),
                # The document label is inherited by every page. Break ties using
                # this chunk's contents so translated type queries open the ID,
                # not an unrelated cover that happens to be first in the file.
                bool(wanted_type and classify(text=h.text) == wanted_type),
            ),
            reverse=True,
        )
        lexical_results = []
        seen_ids = set()
        for hit in lexical_hits:
            if hit.memory_id in seen_ids:
                continue
            seen_ids.add(hit.memory_id)
            lexical_results.append(
                DocumentResult(
                    rank=len(lexical_results) + 1,
                    memory_id=hit.memory_id,
                    title=hit.title,
                    filename=hit.filename,
                    source_type=hit.source_type,
                    score=0.0,
                    raw_score=0.0,
                    snippet=excerpt(hit.text, f"{payload.query} {wanted_type or ''}"),
                    matched_chunk_id=hit.chunk_id,
                    page=hit.page,
                    byte_size=hit.byte_size,
                    has_thumbnail=hit.has_thumbnail,
                    document_type=hit.document_type,
                    removed_at=hit.removed_at,
                )
            )
            if len(lexical_results) >= payload.limit * 2:
                break
        lexical_ids = {r.memory_id for r in lexical_results}
        by_id = {r.memory_id: r for r in [*lexical_results, *ranked]}
        # Preserve dense confidence, but open the chunk that contains the query words.
        from memora.services.lexical import tokens

        query_terms = set(tokens(payload.query))
        for result in lexical_results:
            current = by_id[result.memory_id]
            lexical_evidence = (
                len(query_terms & set(tokens(result.snippet))),
                bool(wanted_type and classify(text=result.snippet) == wanted_type),
            )
            dense_evidence = (
                len(query_terms & set(tokens(current.snippet))),
                bool(wanted_type and classify(text=current.snippet) == wanted_type),
            )
            if lexical_evidence > dense_evidence:
                by_id[result.memory_id] = replace(
                    current, snippet=result.snippet, page=result.page,
                    matched_chunk_id=result.matched_chunk_id,
                )
        fusion: dict = {}
        for arm in (ranked, lexical_results):
            for position, result in enumerate(arm, 1):
                fusion[result.memory_id] = fusion.get(result.memory_id, 0.0) + 1 / (60 + position)
        ordered = sorted(
            by_id.values(),
            key=lambda r: (
                bool(wanted_type and r.document_type == wanted_type),
                fusion[r.memory_id],
                r.score,
            ),
            reverse=True,
        )
        ranked = [replace(r, rank=i) for i, r in enumerate(ordered[: payload.limit], 1)]

    # The image list, fused in by RANK. Some documents have no text at all - a photo of
    # people yields an empty OCR string - so the text list cannot contain them at any
    # quality. Their vector is CLIP's, on a scale where 0.28 is strong, and it is never
    # compared with the text similarities. See services/fusion.py.
    image_hits: list[ImageHit] = []
    if payload.images and image_embedder is not None:
        try:
            async with asyncio.timeout(2):
                clip_vector, _ = await image_embedder.embed_text(payload.query)
            image_hits = await ImageEmbeddingRepository(session, user_id).search(
                clip_vector, payload.limit * 2
            )
        except (ImageEmbeddingUnavailable, TimeoutError):
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
    text_found = {result.memory_id for result in ranked}
    image_evidence = [
        hit
        for hit in image_hits
        if hit.memory_id not in text_found and not has_weak_image_evidence([hit.similarity])
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
        ranked = fuse_results(ranked, image_evidence, payload.limit, wanted_type=wanted_type)

    if wanted_type:
        ranked = [
            replace(r, rank=i)
            for i, r in enumerate((r for r in ranked if r.document_type in (None, wanted_type)), 1)
        ]

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

    # A recognised document type that the corpus holds corroborates a low dense score, so
    # short queries like "pan" or "cv" are not refused for scoring in the embedder's noise.
    type_corroborated = bool(wanted_type) and any(r.document_type == wanted_type for r in ranked)
    settings = get_settings()
    minimum = (
        settings.local_min_similarity
        if settings.embedding_provider == "local"
        else MIN_SIMILARITY_UNCALIBRATED
    )
    text_weak = (
        not lexical_ids
        and not type_corroborated
        and has_weak_evidence([outcome.raw_top_score] if outcome.results else [], minimum)
    )
    image_weak = not image_evidence
    if not ranked or type_mismatch or (text_weak and image_weak):
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
            degraded_message=embedding_degraded
            or (describe(health().status()) if payload.stage1 else None),
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
        stage1_failure_reason=(filters.failure_reason if filters.failed and not skipped else None),
        stage1_skipped=skipped,
        stage1_skip_reason=why(payload.query) if skipped else None,
        degraded_message=embedding_degraded
        or (describe(health().status()) if payload.stage1 else None),
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
                thumbnail_url=(f"/memories/{r.memory_id}/thumbnail" if r.has_thumbnail else None),
                file_url=f"/memories/{r.memory_id}/file",
                removed_at=r.removed_at.isoformat() if r.removed_at else None,
                document_type=r.document_type,
                document_label=r.document_type.replace("_", " ").title()
                if r.document_type
                else None,
                match_explanation=(
                    "Recognized document type from contents or filename"
                    if wanted_type and r.document_type == wanted_type
                    else "Matched words in the document or filename"
                    if r.memory_id in lexical_ids
                    else "Similar meaning or visual appearance — check the preview"
                ),
                uncertain=is_uncertain(
                    local=settings.embedding_provider == "local",
                    in_lexical=r.memory_id in lexical_ids,
                    type_match=bool(wanted_type and r.document_type == wanted_type),
                    raw_score=r.raw_score,
                ),
            )
            for r in ranked
        ],
    )
