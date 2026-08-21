"""Grounded question answering."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from memora.api.deps import CurrentUserDep, DbDep, SettingsDep
from memora.repositories.chunk import ChunkRepository
from memora.services.embedding import Embedder, build_embedder
from memora.services.generation import Generator, build_generator
from memora.services.retrieval import has_weak_evidence

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class CitationOut(BaseModel):
    chunk_id: str
    memory_id: str
    title: str
    snippet: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    refused: bool
    refusal_reason: str | None = None


def get_embedder() -> Embedder:
    return build_embedder()


def get_generator() -> Generator:
    return build_generator()


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
GeneratorDep = Annotated[Generator, Depends(get_generator)]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    session: DbDep,
    user_id: CurrentUserDep,
    settings: SettingsDep,
    embedder: EmbedderDep,
    generator: GeneratorDep,
) -> ChatResponse:
    query_vector = (await embedder.embed([payload.question]))[0]

    chunks = ChunkRepository(session, user_id)
    results = await chunks.search_dense(query_vector, settings.retrieval_top_k)

    if has_weak_evidence(results):
        # Decided before the LLM is reachable. A model asked to refuse will sometimes
        # answer anyway, so the refusal is not delegated to it.
        return ChatResponse(
            answer="I don't have that in your memories.",
            citations=[],
            refused=True,
            refusal_reason="no_evidence" if not results else "weak_evidence",
        )

    answer = await generator.generate(payload.question, results)

    return ChatResponse(
        answer=answer,
        citations=[
            CitationOut(
                chunk_id=str(r.chunk.id),
                memory_id=str(r.chunk.memory_id),
                title=r.chunk.contextual_prefix,
                snippet=r.chunk.text[:280],
                score=round(r.similarity, 4),
            )
            for r in results
        ],
        refused=False,
    )
