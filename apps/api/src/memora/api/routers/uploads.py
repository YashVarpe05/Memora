"""Document ingestion. PDFs and images."""

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
from memora.services.extraction import (
    extract_blocks,
    extract_image_blocks,
    extract_pdf_via_ocr,
    image_mime,
    is_pdf,
)
from memora.services.masking import mask_all
from memora.services.ocr import OcrClient, OcrUnavailable, build_ocr_client

router = APIRouter(tags=["uploads"])

MAX_BYTES = 25 * 1024 * 1024


class UploadResponse(BaseModel):
    memory_id: str
    title: str
    source_type: str
    chunks: int
    identifiers_masked: int


def get_embedder() -> Embedder:
    return build_embedder()


def get_counter() -> TokenCounter:
    return TiktokenCounter()


def get_ocr() -> OcrClient:
    return build_ocr_client()


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
CounterDep = Annotated[TokenCounter, Depends(get_counter)]
OcrDep = Annotated[OcrClient, Depends(get_ocr)]
DocumentUpload = Annotated[UploadFile, File(...)]


@router.post("/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: DbDep,
    user_id: CurrentUserDep,
    file: DocumentUpload,
    embedder: EmbedderDep,
    counter: CounterDep,
    ocr: OcrDep,
) -> UploadResponse:
    data = await file.read()
    filename = file.filename or "upload"

    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 25 MB")

    if is_pdf(data):
        source_type = "pdf"
        title, blocks = extract_blocks(data)
        if not blocks:
            # A printed email or a scan: pages are images, so read them as images.
            try:
                title, blocks = await extract_pdf_via_ocr(data, ocr, filename)
            except OcrUnavailable as exc:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    f"This PDF has no text layer and OCR is unavailable: {exc}",
                ) from exc
    elif image_mime(data):
        source_type = "image"
        try:
            title, blocks = await extract_image_blocks(data, ocr, filename)
        except OcrUnavailable as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                f"OCR is required for images and is not available: {exc}",
            ) from exc
    else:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Only PDF and image uploads are supported.",
        )

    text_chunks = chunk_blocks(blocks, title=title, counter=counter)
    if not text_chunks:
        detail = (
            "No text found in this image."
            if source_type == "image"
            else "No extractable text. A scanned PDF is read through OCR as an image."
        )
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)

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
        source_type=source_type,
        title=title,
        # Stored as data. Never joined onto a path.
        filename=filename,
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

    # Counted by type only, never by value.
    masked_count = sum(len(m.detections) for m in [*masked_text, *masked_prefix])

    return UploadResponse(
        memory_id=str(memory.id),
        title=title,
        source_type=source_type,
        chunks=len(text_chunks),
        identifiers_masked=masked_count,
    )
