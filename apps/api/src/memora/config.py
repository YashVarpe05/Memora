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
    gemini_model: str = "gemini-2.5-flash"
    embedding_model: str = "gemini-embedding-001"
    # Pinned in DDL as vector(768). gemini-embedding-001 defaults to 3072, so this
    # is requested explicitly via output_dimensionality. Changing it needs a migration.
    embedding_dims: int = 768

    retrieval_top_k: int = 5

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
