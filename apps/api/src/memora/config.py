"""Application settings. Config comes from the environment only — never hardcoded."""

from functools import lru_cache
from typing import Literal
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
    embedding_provider: Literal["gemini", "lexical", "local"] = "gemini"
    local_embedding_model: str = "intfloat/multilingual-e5-base"
    local_embedding_revision: str = "d128750597153bb5987e10b1c3493a34e5a4502a"
    local_embedding_threads: int = 2
    # Cross-encoder reranking of the top results (prompts/reranker.md). Ranking only, never
    # refusal. Off by default: it needs the weights downloaded and about 0.9 s of CPU per search.
    reranker: Literal["off", "local"] = "off"
    reranker_model_path: str = "~/.cache/memora-models/mmarco-mMiniLMv2-L12-H384-v1-1427fd65"
    reranker_top_n: int = 20
    reranker_threads: int = 2
    # Weak-evidence floor on multilingual-e5-base's scale, which is not Gemini's: real hits
    # and unrelated queries both score 0.75-0.85, so this only means something together with
    # the lexical and document-type corroboration in the search router.
    #
    # 0.78 is the highest value that falsely refused 0 of 25 answerable queries on a
    # synthetic 16-document pack (0.80 and above lost "cv"); it refuses 3 of 9 absent
    # queries, up from 1. Chosen to avoid hiding a real document, NOT calibrated on real
    # documents - see prompts/refusal-calibration-local-e5.md.
    local_min_similarity: float = 0.78
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
    pairing_store: str = "data/auth/devices.sqlite3"
    operator_secret: str | None = None
    public_api_url: str | None = None
    # Fast, deterministic query filters by default. Local/hosted model arms remain
    # available for comparison through STAGE1_PROVIDER=local or gemini.
    stage1_provider: str = "rules"
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

    # Who may call this API from a browser engine.
    #
    # The Vite dev server is the laptop. The bare-`localhost` entries are the phone: a
    # Capacitor WebView serves the bundled app from `http://localhost` with NO port, so
    # `http://localhost:5173` does not match it and every request from the phone died on
    # the CORS preflight - `OPTIONS /pair/claim` 400 "Disallowed CORS origin". The app
    # reported that as "Could not reach your computer", which reads as a network fault and
    # is why this cost an afternoon. The scheme follows `androidScheme` in
    # capacitor.config.ts; `capacitor://localhost` is the iOS origin, listed so a future
    # iOS build does not rediscover this.
    #
    # This is not the access control. Pairing is: every document route still requires a
    # device token, so a permitted origin only means the browser will deliver the reply.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost",
        "https://localhost",
        "capacitor://localhost",
    ]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
