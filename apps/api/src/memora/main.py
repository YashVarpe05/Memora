"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from memora.api.routers import chat, files, health, search, uploads
from memora.config import get_settings
from memora.db.session import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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
    app.include_router(uploads.router)
    app.include_router(chat.router)
    app.include_router(files.router)
    app.include_router(search.router)
    return app


app = create_app()
