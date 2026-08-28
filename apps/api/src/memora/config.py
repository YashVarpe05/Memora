"""Application settings. Config comes from the environment only — never hardcoded."""

from functools import lru_cache
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Memora API"
    environment: str = "development"

    # Runtime connection. memora_app is NOSUPERUSER + NOBYPASSRLS, so RLS policies
    # actually apply. Never point this at the owner role.
    database_url: str = "postgresql+asyncpg://memora_app:memora_app@localhost:5433/memora"

    # Migrations only. Owns the schema, and in the dev image is a superuser.
    migration_database_url: str = "postgresql+asyncpg://memora:memora@localhost:5433/memora"
    redis_url: str = "redis://localhost:6379/0"

    gemini_api_key: str | None = None
    # Measured 2026-08-24: free-tier generateContent is 20 requests/day PER MODEL, and
    # stage 1 is one call per query, so a 21-query eval does not fit in one model's
    # daily budget. The fix is the stage 1 cache, NOT a different model: switching to
    # gemini-flash-lite-latest for headroom dropped Recall@1 from 0.947 to 0.789,
    # because a weaker extractor produces wrong filters and a wrong filter actively
    # demotes the correct answer. Changing this changes what is being measured.
    gemini_model: str = "gemini-2.5-flash"
    embedding_model: str = "gemini-embedding-001"
    # Pinned in DDL as vector(768). gemini-embedding-001 defaults to 3072, so this
    # is requested explicitly via output_dimensionality. Changing it needs a migration.
    embedding_dims: int = 768

    retrieval_top_k: int = 5

    # Cache stage 1 extractions by query text AND prompt. For evaluation only: the
    # gold set runs the same 21 strings, so a warm cache makes repeat runs free.
    stage1_cache: bool = False

    # OCR runs in a container (infra/ocr), bound to loopback.
    ocr_url: str = "http://localhost:8081"
    # Local stage 1. Loopback only - it holds no credentials and reaches nothing.
    ollama_url: str = "http://localhost:11434"
    # Port the phone reaches. Baked into the pairing QR.
    api_port: int = 8000
    # Require a paired device token from anything that is not loopback.
    #
    # The demo network is a phone hotspot and the API serves the owner's identity
    # documents, so anyone else who joins can otherwise read them. This is the difference
    # between "nothing leaves devices you own" being true and being aspirational.
    require_pairing: bool = True
    # Which model runs stage 1. Local is the DEFAULT, not a fallback: measured at
    # Recall@1 0.895 against a 0.842 dense baseline, with no quota, no deprecation risk,
    # and the query never leaving the machine. See docs/PHASE3-LOCAL.md.
    #
    # Set STAGE1_PROVIDER=gemini to run the hosted comparison arm, which scores 0.947 -
    # one gold row better, and unreproducible by anyone without a pre-cutoff API key.
    stage1_provider: str = "local"
    local_stage1_model: str = "qwen2.5:3b-instruct"
    ocr_engine: str = "tesseract"

    # Blob root. The path of any single file is derived from user_id + hash, so
    # moving this is a config change rather than a data migration.
    blob_root: str = "data/blobs"

    # Phase 1 has no auth. One server-side dev identity, injected exactly the way a
    # real one will be - never read from a request.
    dev_user_id: UUID = UUID("00000000-0000-4000-8000-000000000001")

    jwt_secret: str = "dev-only-change-me"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 30

    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    token_encryption_key: str | None = None

    # Vite dev server
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
