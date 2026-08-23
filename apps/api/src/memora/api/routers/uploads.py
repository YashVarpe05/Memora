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
from memora.services.storage import BlobStore, build_blob_store, make_thumbnail

router = APIRouter(tags=["uploads"])

MAX_BYTES = 25 * 1024 * 1024


class UploadResponse(BaseModel):
    memory_id: str
    title: str
    source_type: str
    chunks: int
    identifiers_masked: int
    deduplicated: bool


def get_embedder() -> Embedder:
    return build_embedder()


def get_counter() -> TokenCounter:
    return TiktokenCounter()


def get_ocr() -> OcrClient:
    return build_ocr_client()


def get_blob_store() -> BlobStore:
    return build_blob_store()


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
CounterDep = Annotated[TokenCounter, Depends(get_counter)]
OcrDep = Annotated[OcrClient, Depends(get_ocr)]
BlobStoreDep = Annotated[BlobStore, Depends(get_blob_store)]
DocumentUpload = Annotated[UploadFile, File(...)]


@router.post("/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: DbDep,
    user_id: CurrentUserDep,
    file: DocumentUpload,
    embedder: EmbedderDep,
    counter: CounterDep,
    ocr: OcrDep,
    blobs: BlobStoreDep,
) -> UploadResponse:
    data = await file.read()
    filename = file.filename or "upload"

    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 25 MB")

    memories = MemoryRepository(session, user_id)

    # Store the bytes first. Extraction can fail; the document should still be on disk
    # and re-processable rather than lost with the request.
    stored = blobs.put(user_id, data)
    existing = await memories.find_by_hash(stored.content_hash)
    if existing is not None:
        # Same owner, same bytes. Nothing to re-ingest.
        chunk_count = await ChunkRepository(session, user_id).count_for_memory(existing.id)
        return UploadResponse(
            memory_id=str(existing.id),
            title=existing.title,
            source_type=existing.source_type,
            chunks=chunk_count,
            identifiers_masked=0,
            deduplicated=True,
        )

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

    chunks = ChunkRepository(session, user_id)

    mime = "application/pdf" if source_type == "pdf" else (image_mime(data) or "")
    thumbnail = make_thumbnail(data, mime)
    if thumbnail:
        blobs.put_thumbnail(user_id, stored.content_hash, thumbnail)

    memory = await memories.create(
        source_type=source_type,
        title=title,
        # Display metadata. Never joined onto a path.
        filename=filename,
        content_hash=stored.content_hash,
        byte_size=stored.byte_size,
        mime_type=mime,
        has_thumbnail=thumbnail is not None,
    )
    await chunks.add_many(
        memory.id,
        [
            Chunk(
                ordinal=c.ordinal,
                text=body.value,
                contextual_prefix=prefix.value,
                token_count=c.token_count,
                page=c.page,
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
        deduplicated=False,
    )
