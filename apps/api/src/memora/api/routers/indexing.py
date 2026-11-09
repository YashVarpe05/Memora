"""Submit once, inspect progress, retry without retransferring document bytes."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from memora.api.deps import CurrentUserDep, DbDep, SettingsDep
from memora.api.routers.search import get_embedder as get_search_embedder
from memora.api.routers.uploads import (
    MAX_BYTES,
    BlobStoreDep,
    CounterDep,
    DevicePath,
    DocumentUpload,
    EmbedderDep,
    UploadResponse,
)
from memora.repositories.embedding_coverage import EmbeddingCoverageRepository
from memora.repositories.index_job import IndexJobRepository
from memora.services.embedding import Embedder, embedding_fingerprint
from memora.services.text_ingest import DevicePage, NoTextError, ingest_device_text

router = APIRouter(tags=["indexing"])


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    status: str
    attempts: int
    error: str | None
    result: dict | None


class JobsResponse(BaseModel):
    counts: dict[str, int]
    jobs: list[JobResponse]


@router.post("/index/jobs", response_model=JobResponse, status_code=202)
async def enqueue(
    session: DbDep,
    user_id: CurrentUserDep,
    file: DocumentUpload,
    blobs: BlobStoreDep,
    device_path: DevicePath = None,
) -> JobResponse:
    if not device_path or len(device_path) > 1024:
        raise HTTPException(422, "A device path of at most 1024 characters is required.")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File exceeds 25 MB.")
    blob = blobs.put(user_id, data)
    job = await IndexJobRepository(session, user_id).enqueue(
        blob.content_hash, (file.filename or "upload")[:512], device_path
    )
    if job.status == "completed":
        from memora.repositories.memory import MemoryRepository

        memories = MemoryRepository(session, user_id)
        memory = await memories.find_by_hash(blob.content_hash)
        if memory is not None:
            await memories.attach_path(memory, device_path)
        else:
            job.status, job.result, job.attempts = "queued", None, 0
            job.retry_at = datetime.now(UTC)
    return JobResponse.model_validate(job)


class DevicePageIn(BaseModel):
    number: int = Field(ge=1, le=10_000)
    text: str = Field(max_length=200_000)


class TextIndexRequest(BaseModel):
    """Text a device extracted itself. The file stays on the device."""

    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    filename: str = Field(min_length=1, max_length=512)
    device_path: str = Field(min_length=1, max_length=1024)
    mime_type: str = Field(default="", max_length=128)
    byte_size: int = Field(default=0, ge=0, le=MAX_BYTES)
    pages: list[DevicePageIn] = Field(min_length=1, max_length=500)


MAX_DEVICE_TEXT = 500_000


@router.post("/index/text-jobs", response_model=UploadResponse, status_code=201)
async def index_device_text(
    payload: TextIndexRequest,
    session: DbDep,
    user_id: CurrentUserDep,
    embedder: EmbedderDep,
    counter: CounterDep,
) -> UploadResponse:
    if sum(len(p.text) for p in payload.pages) > MAX_DEVICE_TEXT:
        raise HTTPException(413, "Extracted text exceeds 500,000 characters.")
    try:
        result = await ingest_device_text(
            session,
            user_id,
            content_hash=payload.content_hash,
            filename=payload.filename,
            device_path=payload.device_path,
            mime_type=payload.mime_type,
            byte_size=payload.byte_size,
            pages=[DevicePage(p.number, p.text) for p in payload.pages],
            embedder=embedder,
            counter=counter,
        )
    except NoTextError as exc:
        raise HTTPException(422, str(exc)) from exc
    return UploadResponse(
        memory_id=str(result.memory_id),
        title=result.title,
        source_type=result.source_type,
        chunks=result.chunks,
        identifiers_masked=result.identifiers_masked,
        deduplicated=result.deduplicated,
    )


@router.get("/index/jobs", response_model=JobsResponse)
async def jobs(
    session: DbDep,
    user_id: CurrentUserDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> JobsResponse:
    repo = IndexJobRepository(session, user_id)
    return JobsResponse(
        counts=await repo.counts(),
        jobs=[JobResponse.model_validate(j) for j in await repo.recent(limit, offset)],
    )


@router.get("/index/jobs/{job_id}", response_model=JobResponse)
async def job_status(job_id: UUID, session: DbDep, user_id: CurrentUserDep) -> JobResponse:
    job = await IndexJobRepository(session, user_id).get(job_id)
    if not job:
        raise HTTPException(404, "Indexing job not found.")
    return JobResponse.model_validate(job)


@router.post("/index/jobs/{job_id}/retry", response_model=JobResponse)
async def retry(job_id: UUID, session: DbDep, user_id: CurrentUserDep) -> JobResponse:
    job = await IndexJobRepository(session, user_id).get(job_id)
    if not job:
        raise HTTPException(404, "Indexing job not found.")
    if job.status == "failed":
        job.status, job.error, job.attempts = "queued", None, 0
        job.retry_at = job.updated_at = datetime.now(UTC)
    return JobResponse.model_validate(job)


class EmbeddingCoverageResponse(BaseModel):
    provider: str
    configured: bool
    # None for remote providers: configuration is not proof of their availability.
    model_ready: bool | None
    available_documents: int
    text_documents: int
    semantic_documents: int
    pending_documents: int
    no_text_documents: int


@router.get("/index/coverage", response_model=EmbeddingCoverageResponse)
async def embedding_coverage(
    session: DbDep,
    user_id: CurrentUserDep,
    settings: SettingsDep,
    embedder: Annotated[Embedder | None, Depends(get_search_embedder)],
) -> EmbeddingCoverageResponse:
    model_id = embedding_fingerprint(embedder)
    return EmbeddingCoverageResponse(
        provider=settings.embedding_provider,
        configured=embedder is not None,
        model_ready=getattr(embedder, "ready", None),
        **await EmbeddingCoverageRepository(session, user_id).counts(model_id),
    )
