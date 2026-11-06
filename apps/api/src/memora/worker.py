"""Durable indexing worker: python -m memora.worker. Safe to restart mid-document."""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, UploadFile

from memora.api.routers.uploads import (
    get_blob_store,
    get_counter,
    get_embedder,
    get_image_embedder,
    get_ocr,
    upload_document,
)
from memora.config import get_settings
from memora.db.models.index_job import IndexJob
from memora.db.session import scoped_session
from memora.repositories.index_job import IndexJobRepository
from memora.services.pairing import store

logger = logging.getLogger(__name__)


async def process_one(user_id: UUID, *, dependencies: dict | None = None) -> bool:
    async for session in scoped_session(user_id):
        job = await IndexJobRepository(session, user_id).next()
        if job is None:
            return False
        job.status = "processing"
        job_id = job.id
    # Persist the visible status first. The second transaction locks the work through
    # ingestion; a crash rolls it back and leaves the processing job resumable.
    async for session in scoped_session(user_id):
        repo = IndexJobRepository(session, user_id)
        job = (
            await session.execute(
                repo.scoped().where(IndexJob.id == job_id).with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if not job or job.status not in ("queued", "processing"):
            return False
        job.attempts += 1
        try:
            async with session.begin_nested(), asyncio.timeout(600):
                deps = dependencies or dict(
                    embedder=get_embedder(),
                    counter=get_counter(),
                    ocr=get_ocr(),
                    image_embedder=get_image_embedder(),
                    blobs=get_blob_store(),
                )
                data = deps["blobs"].read(user_id, job.content_hash)
                response = await upload_document(
                    session=session,
                    user_id=user_id,
                    file=UploadFile(file=io.BytesIO(data), filename=job.filename),
                    device_path=job.device_path,
                    **deps,
                )
            job.result = response.model_dump()
            job.status, job.error = "completed", None
        except Exception as exc:
            permanent = isinstance(exc, HTTPException) and 400 <= exc.status_code < 500
            job.status = "failed" if permanent or job.attempts >= 5 else "queued"
            # Do not persist provider exceptions, request bodies or credentials.
            job.error = (
                str(exc.detail)[:1024]
                if permanent
                else "Processing was interrupted or a service is unavailable. Retry is available."
            )
            job.retry_at = datetime.now(UTC) + timedelta(seconds=min(300, 5 * 2**job.attempts))
        job.updated_at = datetime.now(UTC)
    return True


async def run() -> None:
    while True:
        did_work = False
        identities = store().identities()
        if not get_settings().is_production:
            identities.append(get_settings().dev_user_id)
        for identity in identities:
            try:
                did_work = await process_one(identity) or did_work
            except Exception:
                logger.error("Index worker could not reach its storage; retrying.")
        if not did_work:
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(run())
