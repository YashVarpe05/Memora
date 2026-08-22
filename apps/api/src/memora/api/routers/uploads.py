"""PDF ingestion."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from memora.api.deps import CurrentUserDep, DbDep
from memora.db.models.chunk import Chunk
from memora.repositories.chunk import ChunkRepository
from memora.repositories.memory import MemoryRepository
from memora.services.chunking import TiktokenCounter, TokenCounter, chunk_blocks
from memora.services.embedding import Embedder, build_embedder
from memora.services.extraction import extract_blocks, is_pdf
from memora.services.masking import mask_all

router = APIRouter(tags=["uploads"])

MAX_BYTES = 25 * 1024 * 1024


class UploadResponse(BaseModel):
    memory_id: str
    title: str
    chunks: int


def get_embedder() -> Embedder:
    return build_embedder()


def get_counter() -> TokenCounter:
    return TiktokenCounter()


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
CounterDep = Annotated[TokenCounter, Depends(get_counter)]
PdfUpload = Annotated[UploadFile, File(...)]


@router.post("/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    session: DbDep,
    user_id: CurrentUserDep,
    file: PdfUpload,
    embedder: EmbedderDep,
    counter: CounterDep,
) -> UploadResponse:
    data = await file.read()

    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 25 MB")
    if not is_pdf(data):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Only PDF is supported in this phase.",
        )

    title, blocks = extract_blocks(data)
    text_chunks = chunk_blocks(blocks, title=title, counter=counter)
    if not text_chunks:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "No extractable text. A scanned PDF needs OCR, which arrives in phase 4.",
        )

    # Masked before embedding, and the masked form is what gets stored - so the
    # number is absent from the index as well as from the request.
    # Mask once, then use the masked form for everything downstream. Masking only the
    # embed payload would keep the number out of the request and leave it sitting in
    # the database, which is not what "never leaves the machine" means.
    masked_text = mask_all([c.text for c in text_chunks])
    masked_prefix = mask_all([c.contextual_prefix for c in text_chunks])

    vectors = await embedder.embed(
        mask_all(
            [
                f"{prefix.value}\n\n{body.value}" if prefix.value else body.value
                for prefix, body in zip(masked_prefix, masked_text, strict=True)
            ]
        )
    )

    memories = MemoryRepository(session, user_id)
    chunks = ChunkRepository(session, user_id)

    memory = await memories.create(
        source_type="pdf",
        title=title,
        # Stored as data. Never joined onto a path.
        filename=file.filename or "upload.pdf",
    )
    await chunks.add_many(
        memory.id,
        [
            Chunk(
                ordinal=c.ordinal,
                text=body.value,
                contextual_prefix=prefix.value,
                token_count=c.token_count,
                embedding=vector,
            )
            for c, body, prefix, vector in zip(
                text_chunks, masked_text, masked_prefix, vectors, strict=True
            )
        ],
    )

    return UploadResponse(memory_id=str(memory.id), title=title, chunks=len(text_chunks))
