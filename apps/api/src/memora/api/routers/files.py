"""Serving and deleting stored documents.

Every lookup goes through the repository, so RLS and the per-owner scope both apply.
A blob path is never accepted from a request - it is derived from the owner and the
hash on a row the caller is already allowed to read.
"""

from __future__ import annotations

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from memora.api.deps import CurrentUserDep, DbDep
from memora.repositories.memory import MemoryRepository
from memora.services.storage import BlobStore, build_blob_store

router = APIRouter(tags=["files"])

# Anything outside this is replaced before the name goes in a header.
_UNSAFE_FILENAME = re.compile(r'[^A-Za-z0-9._ -]')


def get_blob_store() -> BlobStore:
    return build_blob_store()


BlobStoreDep = Annotated[BlobStore, Depends(get_blob_store)]


def safe_filename(name: str) -> str:
    cleaned = _UNSAFE_FILENAME.sub("_", name).strip() or "download"
    return cleaned[:200]


@router.get("/memories/{memory_id}/file")
async def get_file(
    memory_id: UUID,
    session: DbDep,
    user_id: CurrentUserDep,
    blobs: BlobStoreDep,
) -> Response:
    memory = await MemoryRepository(session, user_id).get(memory_id)
    if memory is None or not memory.content_hash:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if not blobs.exists(user_id, memory.content_hash):
        raise HTTPException(status.HTTP_410_GONE, "The stored file is missing")

    return Response(
        content=blobs.read(user_id, memory.content_hash),
        media_type=memory.mime_type or "application/octet-stream",
        headers={
            # attachment, always. An uploaded HTML file must never render on this origin.
            "Content-Disposition": f'attachment; filename="{safe_filename(memory.filename)}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/memories/{memory_id}/thumbnail")
async def get_thumbnail(
    memory_id: UUID,
    session: DbDep,
    user_id: CurrentUserDep,
    blobs: BlobStoreDep,
) -> Response:
    memory = await MemoryRepository(session, user_id).get(memory_id)
    if memory is None or not memory.has_thumbnail:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No thumbnail")

    path = blobs.thumbnail_path(user_id, memory.content_hash)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No thumbnail")

    return Response(
        content=path.read_bytes(),
        media_type="image/jpeg",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=86400",
        },
    )


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: UUID,
    session: DbDep,
    user_id: CurrentUserDep,
    blobs: BlobStoreDep,
) -> Response:
    """Rows, vectors and the file itself.

    PRODUCT.md claims erasure is demonstrable. A row removed while the document survives
    on disk is not erasure, so the blob goes with it.
    """
    memory = await MemoryRepository(session, user_id).delete(memory_id)
    if memory is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    if memory.content_hash:
        blobs.delete(user_id, memory.content_hash)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
