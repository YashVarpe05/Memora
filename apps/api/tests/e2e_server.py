"""Isolated E2E server: real PostgreSQL, extraction and OCR; fake model embeddings.

Never a production entrypoint. Started and stopped by the Playwright harness.
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
from contextlib import asynccontextmanager, suppress
from pathlib import Path

STATE = Path(os.environ["MEMORA_E2E_STATE"]).resolve()
STATE.mkdir(parents=True, exist_ok=True)
os.environ.update(
    ENVIRONMENT="development",
    DATABASE_URL=os.getenv(
        "MEMORA_E2E_DATABASE_URL",
        "postgresql+asyncpg://memora_app:memora_app@127.0.0.1:5433/memora",
    ),
    PAIRING_STORE=str(STATE / "auth.sqlite"),
    BLOB_ROOT=str(STATE / "blobs"),
    STAGE1_PROVIDER="rules",
    EMBEDDING_PROVIDER="lexical" if os.getenv("MEMORA_E2E_LEXICAL") == "1" else "gemini",
    GEMINI_API_KEY="",
    OPERATOR_SECRET="",
)

import pymupdf  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from sqlalchemy import text  # noqa: E402

from memora.api.routers import files, search, uploads  # noqa: E402
from memora.db.session import dispose_engine, scoped_session  # noqa: E402
from memora.main import create_app  # noqa: E402
from memora.repositories.index_job import IndexJobRepository  # noqa: E402
from memora.repositories.memory import MemoryRepository  # noqa: E402
from memora.services.pairing import store  # noqa: E402
from memora.services.rules_query_understanding import RulesQueryUnderstanding  # noqa: E402
from memora.services.storage import BlobStore  # noqa: E402
from memora.worker import process_one  # noqa: E402

from support import FakeCounter, FakeEmbedder, FakeImageEmbedder, make_pdf  # noqa: E402


class RealTesseract:
    async def read(self, data: bytes, filename: str = "upload") -> str:
        proc = await asyncio.create_subprocess_exec(
            "tesseract", "stdin", "stdout", "-l", "eng", "--psm", "6",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(data)
        if proc.returncode:
            raise RuntimeError(f"Tesseract failed: {stderr.decode()[:200]}")
        return stdout.decode()


def create_fixtures() -> None:
    folder = STATE / "fixtures"
    folder.mkdir(exist_ok=True)
    image = Image.new("RGB", (1600, 650), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=60)
    draw.multiline_text(
        (60, 60), "AADHAAR CARD\nUnique Identification Authority of India\nSYNTHETIC TEST ONLY",
        font=font, fill="black", spacing=24,
    )
    png = io.BytesIO()
    image.save(png, format="PNG")
    with pymupdf.open() as doc:
        cover = doc.new_page()
        cover.insert_text((72, 72), "Synthetic cover page - details on next page")
        page = doc.new_page(width=800, height=325)
        page.insert_image(page.rect, stream=png.getvalue())
        aadhaar = doc.tobytes()
    (folder / "2344646563rt.pdf").write_bytes(aadhaar)
    (folder / "8349201.pdf").write_bytes(
        make_pdf(["Statement of Marks\nSemester 6\nSYNTHETIC TEST ONLY"])
    )
    (folder / "987654321.txt").write_text("Electricity bill\nMarch 2026\nSynthetic test only")
    (folder / "unsupported.xyz").write_text("Synthetic unsupported file")


app = create_app()
deps = dict(
    embedder=FakeEmbedder(), counter=FakeCounter(), image_embedder=FakeImageEmbedder(),
    ocr=RealTesseract(), blobs=BlobStore(STATE / "blobs"),
)
if os.getenv("MEMORA_E2E_LEXICAL") == "1":
    deps["embedder"] = None
    deps["image_embedder"] = None

for getter, name in [
    (uploads.get_embedder, "embedder"), (uploads.get_counter, "counter"),
    (uploads.get_image_embedder, "image_embedder"), (uploads.get_ocr, "ocr"),
    (uploads.get_blob_store, "blobs"), (search.get_embedder, "embedder"),
    (search.get_image_embedder, "image_embedder"), (files.get_blob_store, "blobs"),
]:
    app.dependency_overrides[getter] = lambda name=name: deps[name]
app.dependency_overrides[search.get_query_understanding] = RulesQueryUnderstanding


async def worker():
    while True:
        for identity in store().identities():
            await process_one(identity, dependencies=deps)
        await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(_):
    if not shutil.which("tesseract"):
        raise RuntimeError("E2E requires real Tesseract and its English language pack.")
    from memora.config import get_settings

    # Startup must fail, not skip, if the real database/schema is unavailable.
    async for session in scoped_session(get_settings().dev_user_id):
        assert await session.scalar(text(
            "SELECT NOT rolsuper AND NOT rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        ))
        await session.execute(text("SELECT id FROM index_jobs LIMIT 0"))
    create_fixtures()
    task = asyncio.create_task(worker())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        # The private SQLite store contains only identities created by this run.
        for identity in store().identities():
            async for session in scoped_session(identity):
                jobs = IndexJobRepository(session, identity)
                for job in await jobs.recent(500):
                    await jobs.delete_for_hash(job.content_hash)
                memories = MemoryRepository(session, identity)
                for memory in (await session.execute(memories.scoped())).scalars().all():
                    await memories.delete(memory.id)
        await dispose_engine()


app.router.lifespan_context = lifespan

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("MEMORA_E2E_API_PORT", "18080")))
