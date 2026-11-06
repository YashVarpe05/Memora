"""Liveness and readiness probes."""

from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import text

from memora.api.deps import SessionDep, SettingsDep
from memora.config_provenance import describe as config_origins

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    pgvector: str
    redis: str
    role: str
    # Observed, not probed - checking quota would spend the quota being checked.
    query_understanding: str
    search_mode: str = "hybrid"
    degraded_message: str | None = None
    # Which config source each measurement-critical setting came from. A pin that is
    # silently overridden looks identical to a pin that holds.
    config_sources: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    """Liveness. Touches no external service, so it works before docker compose is up."""
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.environment,
    )


@router.get("/health/ready", response_model=ReadinessResponse, status_code=status.HTTP_200_OK)
async def readiness(session: SessionDep, settings: SettingsDep) -> ReadinessResponse:
    """Readiness. Verifies Postgres, the vector extension, and Redis are actually reachable."""
    database = pgvector = redis_state = "down"
    role = "unknown"

    try:
        await session.execute(text("SELECT 1"))
        database = "up"
        found = await session.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        pgvector = "installed" if found.scalar_one_or_none() else "missing"
        name, bypasses = (
            await session.execute(
                text(
                    "SELECT current_user, rolsuper OR rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).one()
        role = f"{name} (BYPASSES RLS)" if bypasses else f"{name} (rls enforced)"
    except Exception:  # noqa: BLE001 - probe reports state, never raises
        pass

    try:
        from redis.asyncio import Redis

        client = Redis.from_url(settings.redis_url)
        try:
            await client.ping()
            redis_state = "up"
        finally:
            await client.aclose()
    except Exception:  # noqa: BLE001
        pass

    healthy = database == "up" and pgvector == "installed" and redis_state == "up"
    from memora.services.stage1_health import describe, health

    stage1 = health().status()
    overall = "ready" if healthy else "degraded"
    if healthy and stage1.degraded:
        overall = "degraded"
    return ReadinessResponse(
        status=overall,
        database=database,
        pgvector=pgvector,
        redis=redis_state,
        role=role,
        config_sources={
            o.field: (o.source + " (.env IGNORED)" if o.shadowed else o.source)
            for o in config_origins(settings)
        },
        query_understanding=stage1.state,
        search_mode="lexical" if settings.embedding_provider == "lexical" else "hybrid",
        degraded_message=(
            "Word and document-type search is enabled. Meaning-based and visual search "
            "are disabled in this local trial."
            if settings.embedding_provider == "lexical" else describe(stage1)
        ),
    )
