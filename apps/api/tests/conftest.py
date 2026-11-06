"""Test fixtures.

Deliberately no database here. Phase-1 tests must pass before `docker compose up`,
so nothing in this file may require a live service.
"""

from contextlib import suppress

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
    from memora.api.deps import current_user_id, get_db, get_session

    app.dependency_overrides[uploads_router.get_embedder] = lambda: doubles["embedder"]
    app.dependency_overrides[uploads_router.get_counter] = lambda: doubles["counter"]
    app.dependency_overrides[uploads_router.get_ocr] = lambda: doubles["ocr"]
    app.dependency_overrides[uploads_router.get_image_embedder] = (
        lambda: doubles["image_embedder"]
    )
    # The SEARCH router has its own CLIP dependency. Without this override /search calls
    # the real container, and on failure falls into the ImageEmbeddingUnavailable branch
    # silently - so fusion would appear to work in tests while never running.
    app.dependency_overrides[search_router.get_image_embedder] = (
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
    app.dependency_overrides[get_session] = _db
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


# ---------------------------------------------------------------------------
# Double-usage probe.  Run with:  uv run pytest --double-usage
#
# Counts how often each test double is actually CALLED. A structural audit can only
# prove a dependency is overridden; this proves the path it stands in for runs at all.
#
# It exists because the two are not the same. On 2026-08-26 the search router's CLIP
# dependency was not overridden, so every test silently took the "CLIP unavailable"
# branch and passed - hiding a refusal bug that made a hero query structurally
# unreachable. The same probe then showed stage_one.extract being called 5 times across
# the entire suite, because 72% of search-test queries carried no filterable signal and
# the skip heuristic correctly skipped them. Nothing was broken. The coverage was simply
# not there, and a green suite said nothing.
#
# A low count is not automatically a bug. It is a question worth asking.
# ---------------------------------------------------------------------------

_DOUBLE_CALLS: dict[str, int] = {}


def pytest_addoption(parser):
    parser.addoption(
        "--double-usage",
        action="store_true",
        default=False,
        help="report how many times each test double was called",
    )


@pytest.fixture(autouse=True)
def _count_double_calls(request, doubles):
    """Wraps every double method to count calls. Off unless --double-usage is passed,
    so the normal suite pays nothing."""
    if not request.config.getoption("--double-usage"):
        yield
        return

    import inspect

    def counted(fn, key):
        if inspect.iscoroutinefunction(fn):
            async def call_async(*args, **kwargs):
                _DOUBLE_CALLS[key] = _DOUBLE_CALLS.get(key, 0) + 1
                return await fn(*args, **kwargs)

            return call_async

        def call_sync(*args, **kwargs):
            _DOUBLE_CALLS[key] = _DOUBLE_CALLS.get(key, 0) + 1
            return fn(*args, **kwargs)

        return call_sync

    for label, double in doubles.items():
        for name in dir(double):
            if name.startswith("_"):
                continue
            attr = getattr(double, name)
            if callable(attr):
                with suppress(AttributeError, TypeError):
                    setattr(double, name, counted(attr, f"{label}.{name}"))
    yield


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not config.getoption("--double-usage"):
        return
    terminalreporter.write_sep("=", "double usage")
    if not _DOUBLE_CALLS:
        terminalreporter.write_line("no doubles were called at all")
        return
    for key in sorted(_DOUBLE_CALLS, key=lambda k: -_DOUBLE_CALLS[k]):
        terminalreporter.write_line(f"  {_DOUBLE_CALLS[key]:>6}x  {key}")
    terminalreporter.write_line("")
    terminalreporter.write_line(
        "A low count means that path barely runs. Ask why before trusting it."
    )
