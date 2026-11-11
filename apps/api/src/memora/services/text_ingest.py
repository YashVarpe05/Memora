"""Index text that a device already extracted, without ever receiving the file.

The phone keeps the original. The server keeps only masked text, vectors and metadata, so
`/memories/{id}/file` answers 410 for these documents and the file opens on the device.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from memora.db.models.chunk import Chunk
from memora.repositories.chunk import ChunkRepository
from memora.repositories.memory import MemoryRepository
from memora.services.chunking import Block, TokenCounter, chunk_blocks
from memora.services.document_dates import document_date
from memora.services.document_type import classify
from memora.services.embedding import Embedder, embedding_fingerprint
from memora.services.masking import mask_all, mask_name


class NoTextError(ValueError):
    """The device sent nothing searchable."""


@dataclass(frozen=True)
class DevicePage:
    number: int
    text: str


@dataclass(frozen=True)
class TextIngestResult:
    memory_id: UUID
    title: str
    source_type: str
    chunks: int
    identifiers_masked: int
    deduplicated: bool


def _clean(text: str) -> str:
    return text.replace("\x00", "").strip()


def _source_type(mime_type: str) -> str:
    if mime_type == "application/pdf":
        return "pdf"
    if mime_type.startswith("image/"):
        return "image"
    return "note"


async def ingest_device_text(
    session: AsyncSession,
    user_id: UUID,
    *,
    content_hash: str,
    filename: str,
    device_path: str,
    mime_type: str,
    byte_size: int,
    pages: list[DevicePage],
    embedder: Embedder | None,
    counter: TokenCounter,
) -> TextIngestResult:
    memories = MemoryRepository(session, user_id)

    async def already_indexed() -> TextIngestResult | None:
        existing = await memories.find_by_hash(content_hash)
        if existing is None:
            return None
        await memories.attach_path(existing, device_path)
        return TextIngestResult(
            memory_id=existing.id,
            title=existing.title,
            source_type=existing.source_type,
            chunks=await ChunkRepository(session, user_id).count_for_memory(existing.id),
            identifiers_masked=0,
            deduplicated=True,
        )

    # A known document skips the expensive work entirely.
    if (known := await already_indexed()) is not None:
        return known

    # Postgres text cannot hold NUL. A UTF-16 file decoded as UTF-8, or a noisy OCR pass,
    # produces them, and one such file must not fail with a 500.
    blocks = [Block(text=clean, page=p.number) for p in pages if (clean := _clean(p.text))]
    if not blocks:
        raise NoTextError("No text was found in this document.")

    filename = mask_name(filename)
    title = Path(filename).stem or filename
    head = " ".join(b.text for b in blocks)[:1500]
    date = document_date(head)
    if date:
        blocks = [replace(b, occurred_at=date) for b in blocks]
    text_chunks = await asyncio.to_thread(chunk_blocks, blocks, title=title, counter=counter)
    if not text_chunks:
        raise NoTextError("No text was found in this document.")

    # Mask before anything is stored or embedded, whatever the device already masked.
    masked_text = mask_all([c.text for c in text_chunks])
    masked_prefix = mask_all([c.contextual_prefix for c in text_chunks])
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

    # Embedding can take seconds on a CPU server, so the per-document lock is taken only now,
    # just before writing. Same key as a file upload, so two devices sending one document
    # cannot both create it; the loser re-checks and deduplicates instead.
    lock_key = int.from_bytes(
        hashlib.sha256(f"{user_id}:{content_hash}".encode()).digest()[:8], "big", signed=True
    )
    await session.execute(sql_text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    if (raced := await already_indexed()) is not None:
        return raced

    source_type = _source_type(mime_type)
    memory = await memories.create(
        source_type=source_type,
        title=title,
        filename=filename,
        content_hash=content_hash,
        byte_size=byte_size,
        mime_type=mime_type,
        has_thumbnail=False,
        document_type=classify(filename=filename, text=head),
        occurred_at=date,
        device_path=device_path,
    )
    await memories.attach_path(memory, device_path)
    await ChunkRepository(session, user_id).add_many(
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
    return TextIngestResult(
        memory_id=memory.id,
        title=title,
        source_type=source_type,
        chunks=len(text_chunks),
        identifiers_masked=sum(len(m.detections) for m in [*masked_text, *masked_prefix]),
        deduplicated=False,
    )
