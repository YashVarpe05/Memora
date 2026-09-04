"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from memora.api.routers import chat, device, files, health, pairing, search, uploads
from memora.config import get_settings
from memora.db.session import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Which config source won, printed before anything uses it. A shell variable
    # silently shadowing .env made a pinned model look pinned while something else
    # ran - see config_provenance.
    import logging

    from memora.config_provenance import report

    logger = logging.getLogger("memora.config")
    for line in report(get_settings()):
        logger.warning(line)

    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Personal digital-memory system. Grounded answers with citations.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(pairing.router)
    # Everything that touches the user's documents requires a paired device. Applied at
    # registration rather than per-route: a new endpoint is protected by default, and
    # forgetting the decorator cannot quietly expose a corpus.
    #
    # /health and /pair are deliberately outside this - the phone must be able to reach
    # them before it has a token, and neither returns anything private.
    from memora.api.routers.pairing import require_paired_device

    paired = [Depends(require_paired_device)]
    app.include_router(uploads.router, dependencies=paired)
    app.include_router(chat.router, dependencies=paired)
    app.include_router(files.router, dependencies=paired)
    app.include_router(search.router, dependencies=paired)
    app.include_router(device.router, dependencies=paired)
    return app


app = create_app()
