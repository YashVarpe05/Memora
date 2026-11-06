"""Document ingestion. PDFs and images."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from memora.api.deps import CurrentUserDep, DbDep
from memora.config import get_settings
from memora.db.models.chunk import Chunk
from memora.repositories.chunk import ChunkRepository
from memora.repositories.image_embedding import ImageEmbeddingRepository
from memora.repositories.memory import MemoryRepository
from memora.services.chunking import (
    TiktokenCounter,
    TokenCounter,
    chunk_blocks,
    chunk_per_block,
)
from memora.services.document_type import classify
from memora.services.embedding import Embedder, build_embedder, embedding_fingerprint
from memora.services.extraction import (
    DocumentError,
    Extracted,
    extract_calendar,
    extract_chat,
    extract_email,
    extract_image_blocks,
    extract_office_or_text,
    extract_pdf,
    image_mime,
    is_pdf,
    text_kind,
)
from memora.services.image_embedding import (
    ImageEmbedder,
    ImageEmbeddingUnavailable,
    build_image_embedder,
)
from memora.services.masking import mask_all
from memora.services.ocr import OcrClient, OcrUnavailable, build_ocr_client
from memora.services.parsers.chat import UnparseableChatExport
from memora.services.storage import BlobStore, build_blob_store, make_thumbnail

router = APIRouter(tags=["uploads"])

MAX_BYTES = 25 * 1024 * 1024

TEXT_MIME = {
    "calendar": "text/calendar",
    "email": "message/rfc822",
    "chat": "text/plain",
    "document": "application/octet-stream",
}


class UploadResponse(BaseModel):
    memory_id: str
    title: str
    source_type: str
    chunks: int
    identifiers_masked: int
    deduplicated: bool


def get_embedder() -> Embedder | None:
    if get_settings().embedding_provider == "lexical":
        return None
    return build_embedder()


def get_counter() -> TokenCounter:
    return TiktokenCounter()


def get_image_embedder() -> ImageEmbedder | None:
    return build_image_embedder()


def get_ocr() -> OcrClient:
    return build_ocr_client()


def get_blob_store() -> BlobStore:
    return build_blob_store()


EmbedderDep = Annotated[Embedder | None, Depends(get_embedder)]
CounterDep = Annotated[TokenCounter, Depends(get_counter)]
OcrDep = Annotated[OcrClient, Depends(get_ocr)]
ImageEmbedderDep = Annotated[ImageEmbedder | None, Depends(get_image_embedder)]
BlobStoreDep = Annotated[BlobStore, Depends(get_blob_store)]
DocumentUpload = Annotated[UploadFile, File(...)]
# Where the device scan found this file. Absent for a hand-uploaded document, which is
# why it is Optional rather than defaulted to "" - null means "not from a device" and
# empty string would make every browser upload look like a device file that vanished.
DevicePath = Annotated[str | None, Form()]


@router.post("/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: DbDep,
    user_id: CurrentUserDep,
    file: DocumentUpload,
    embedder: EmbedderDep,
    counter: CounterDep,
    ocr: OcrDep,
    image_embedder: ImageEmbedderDep,
    blobs: BlobStoreDep,
    device_path: DevicePath = None,
) -> UploadResponse:
    data = await file.read(MAX_BYTES + 1)
    filename = (file.filename or "upload")[:512]
    if device_path is not None and (not device_path or len(device_path) > 1024):
        raise HTTPException(422, 'Device path must contain 1–1024 characters.')

    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 25 MB")

    memories = MemoryRepository(session, user_id)

    # Store the bytes first. Extraction can fail; the document should still be on disk
    # and re-processable rather than lost with the request.
    stored = blobs.put(user_id, data)
    import hashlib

    from sqlalchemy import text

    lock_key = int.from_bytes(
        hashlib.sha256(f"{user_id}:{stored.content_hash}".encode()).digest()[:8], "big", signed=True
    )
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    existing = await memories.find_by_hash(stored.content_hash)
    if existing is not None:
        if device_path:
            await memories.attach_path(existing, device_path)
        chunk_count = await ChunkRepository(session, user_id).count_for_memory(existing.id)
        return UploadResponse(
            memory_id=str(existing.id),
            title=existing.title,
            source_type=existing.source_type,
            chunks=chunk_count,
            identifiers_masked=0,
            deduplicated=True,
        )

    kind = text_kind(data)

    if is_pdf(data):
        try:
            title, blocks = await extract_pdf(data, ocr, filename)
        except DocumentError as exc:
            raise HTTPException(422, str(exc)) from exc
        except OcrUnavailable as exc:
            raise HTTPException(
                503, "OCR is temporarily unavailable. Indexing will retry."
            ) from exc
        extracted = Extracted(title=title, blocks=blocks, source_type="pdf")
    elif image_mime(data):
        try:
            title, blocks = await extract_image_blocks(data, ocr, filename)
        except OcrUnavailable as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                f"OCR is required for images and is not available: {exc}",
            ) from exc
        extracted = Extracted(title=title, blocks=blocks, source_type="image")
    elif kind == "calendar":
        extracted = extract_calendar(data, filename)
    elif kind == "email":
        extracted = extract_email(data, filename)
    elif kind == "chat":
        try:
            extracted = extract_chat(data, filename)
        except UnparseableChatExport as exc:
            # Loudly, on purpose. A silently unparsed export becomes one enormous chunk
            # that matches nothing, and nobody notices until a search fails.
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    else:
        from pathlib import Path

        if Path(filename).suffix.lower() not in (".txt", ".md", ".doc", ".docx"):
            raise HTTPException(415, "Unsupported format. Choose PDF, image, text or Word.")
        try:
            extracted = await asyncio.to_thread(extract_office_or_text, data, filename)
        except DocumentError as exc:
            raise HTTPException(422, str(exc)) from exc

    from dataclasses import replace

    from memora.services.document_dates import document_date

    if extracted.occurred_at is None:
        date = document_date(" ".join(b.text for b in extracted.blocks)[:1500])
        if date:
            extracted = replace(
                extracted,
                occurred_at=date,
                blocks=[replace(b, occurred_at=b.occurred_at or date) for b in extracted.blocks],
            )
    title, blocks, source_type = extracted.title, extracted.blocks, extracted.source_type

    chunker = chunk_per_block if extracted.per_block else chunk_blocks
    text_chunks = await asyncio.to_thread(chunker, blocks, title=title, counter=counter)

    # An image with no text used to be rejected here, because it was unsearchable: no
    # chunk, no vector, not ranked badly but absent. CLIP changes that - the picture
    # itself becomes the index - so the rule is now "reject only if there is NEITHER
    # text NOR an image embedding".
    can_embed_image = source_type == "image" and image_embedder is not None
    if not text_chunks and not can_embed_image:
        detail = (
            "No text found in this image."
            if source_type == "image"
            else f"No extractable content in this {source_type} file."
        )
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)

    # Mask once, then use the masked form for everything downstream. Masking only the
    # embed payload would keep the number out of the request and leave it sitting in
    # the database, which is not what "never leaves the machine" means.
    masked_text = mask_all([c.text for c in text_chunks])
    masked_prefix = mask_all([c.contextual_prefix for c in text_chunks])

    # NULL means no semantic index, never a fabricated vector. The real masked
    # text still powers BM25/type search in the explicitly selected lexical mode.
    vectors = (
        await embedder.embed(
            mask_all(
                [
                    f"{prefix.value}\n\n{body.value}" if prefix.value else body.value
                    for prefix, body in zip(masked_prefix, masked_text, strict=True)
                ]
            )
        )
        if embedder is not None
        else [None] * len(text_chunks)
    )

    chunks = ChunkRepository(session, user_id)

    mime = (
        "application/pdf"
        if source_type == "pdf"
        else (image_mime(data) or TEXT_MIME.get(source_type, "text/plain"))
    )
    thumbnail = make_thumbnail(data, mime)
    if thumbnail:
        blobs.put_thumbnail(user_id, stored.content_hash, thumbnail)

    # Labelled from the filename and the head of the extracted text. Rule-based and
    # offline: a classifier here would be a second extractor, and PHASE3.md measured
    # what a weak extractor costs.
    document_type = classify(
        filename=filename,
        # The head only. A receipt says so at the top; a calendar that mentions the
        # word once, three hundred events down, is not a receipt.
        text=" ".join(b.text for b in extracted.blocks)[:1500],
    )

    # The image vector, before the row so a CLIP failure does not leave a memory with
    # neither text nor a picture index - which would be a document nothing can find.
    image_vector: list[float] | None = None
    image_model = ""
    if source_type == "image" and image_embedder is not None:
        try:
            image_vector, image_model = await image_embedder.embed_image(data, filename)
        except ImageEmbeddingUnavailable:
            # Degrade, do not fail. A document with text is still fully searchable
            # without its picture vector; one without text is not, and that case is
            # caught below.
            image_vector = None

    if not text_chunks and image_vector is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "No text found in this image, and it could not be indexed visually.",
        )

    memory = await memories.create(
        source_type=source_type,
        title=title,
        # Display metadata. Never joined onto a path.
        filename=filename,
        content_hash=stored.content_hash,
        byte_size=stored.byte_size,
        mime_type=mime,
        has_thumbnail=thumbnail is not None,
        document_type=document_type,
        sender=extracted.sender,
        occurred_at=extracted.occurred_at,
        device_path=device_path,
    )
    if device_path:
        await memories.attach_path(memory, device_path)
    await chunks.add_many(
        memory.id,
        [
            Chunk(
                ordinal=c.ordinal,
                text=body.value,
                contextual_prefix=prefix.value,
                token_count=c.token_count,
                page=c.page,
                occurred_at=c.occurred_at,
                meta=c.meta or {},
                embedding=vector,
                embedding_model=embedding_fingerprint(embedder) if vector is not None else None,
            )
            for c, body, prefix, vector in zip(
                text_chunks, masked_text, masked_prefix, vectors, strict=True
            )
        ],
    )

    if image_vector is not None:
        await ImageEmbeddingRepository(session, user_id).add(memory.id, image_vector, image_model)

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
