"""Test fixtures.

Deliberately no database here. Phase-1 tests must pass before `docker compose up`,
so nothing in this file may require a live service.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from memora.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- database-backed fixtures -------------------------------------------------
# Skipped when Postgres is unreachable, so the suite stays useful with docker down.

import uuid  # noqa: E402

import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import InterfaceError, OperationalError  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from memora.api.routers import chat as chat_router  # noqa: E402
from memora.api.routers import files as files_router  # noqa: E402
from memora.api.routers import search as search_router  # noqa: E402
from memora.api.routers import uploads as uploads_router  # noqa: E402
from memora.config import get_settings  # noqa: E402

# Only these mean "no database". Anything else is a real failure and must not be
# quietly converted into a green skip.
UNREACHABLE = (OSError, InterfaceError, OperationalError)


@pytest.fixture
def test_user_id():
    """A fresh identity per test.

    Not the dev UUID: that one accumulates rows from manual runs against the same
    local database, and a test asserting "the corpus is empty" would then depend on
    what someone last uploaded by hand. A random owner is isolated by RLS itself.
    """
    return uuid.uuid4()


@pytest_asyncio.fixture
async def db(test_user_id):
    """A transaction scoped to this test's user, rolled back afterwards.

    Builds its own engine with NullPool rather than reusing the app's cached one.
    pytest-asyncio gives each test a fresh event loop, and a pooled connection bound
    to a previous loop fails in ways that look nothing like a connection problem.
    """
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        session = async_sessionmaker(engine, expire_on_commit=False)()
        await session.connection()
    except UNREACHABLE as exc:
        await engine.dispose()
        pytest.skip(f"Postgres not reachable: {type(exc).__name__}")

    try:
        await session.execute(
            text("SELECT set_config('app.user_id', :uid, true)"),
            {"uid": str(test_user_id)},
        )
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


@pytest.fixture
def blob_store(tmp_path):
    """Isolated blob root per test, so uploads never write into the repo."""
    from memora.services.storage import BlobStore

    return BlobStore(root=tmp_path / "blobs")


@pytest.fixture
def doubles():
    from support import (
        FakeCounter,
        FakeEmbedder,
        FakeGenerator,
        FakeImageEmbedder,
        FakeOcr,
        FakeStageOne,
    )

    return {
        "embedder": FakeEmbedder(),
        "counter": FakeCounter(),
        "generator": FakeGenerator(),
        "ocr": FakeOcr(),
        "stage_one": FakeStageOne(),
        "image_embedder": FakeImageEmbedder(),
    }


@pytest_asyncio.fixture
async def api(app, db, doubles, test_user_id, blob_store):
    """Client with the LLM, embedder and tokenizer replaced, sharing the test's session."""
    from memora.api.deps import current_user_id, get_db

    app.dependency_overrides[uploads_router.get_embedder] = lambda: doubles["embedder"]
    app.dependency_overrides[uploads_router.get_counter] = lambda: doubles["counter"]
    app.dependency_overrides[uploads_router.get_ocr] = lambda: doubles["ocr"]
    app.dependency_overrides[uploads_router.get_image_embedder] = (
        lambda: doubles["image_embedder"]
    )
    app.dependency_overrides[uploads_router.get_blob_store] = lambda: blob_store
    app.dependency_overrides[files_router.get_blob_store] = lambda: blob_store
    app.dependency_overrides[chat_router.get_embedder] = lambda: doubles["embedder"]
    app.dependency_overrides[search_router.get_embedder] = lambda: doubles["embedder"]
    # Stage 1 is a real API call otherwise - quota, latency and non-determinism.
    app.dependency_overrides[search_router.get_query_understanding] = (
        lambda: doubles["stage_one"]
    )
    app.dependency_overrides[chat_router.get_generator] = lambda: doubles["generator"]

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    # Must match the session var, or RLS WITH CHECK rejects every insert.
    app.dependency_overrides[current_user_id] = lambda: test_user_id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _fresh_stage1_health():
    """Stage 1 health is process-local, so one test's failures would leak into the next."""
    from memora.services import stage1_health

    stage1_health._health = stage1_health.Stage1Health()
    yield
