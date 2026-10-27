from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "WMD-agent"
    environment: str = "development"
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    openai_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    google_search_api_key: str | None = None
    google_search_cx: str | None = None
    serpapi_api_key: str | None = None
    brave_search_api_key: str | None = None
    tavily_api_key: str | None = None
    exa_api_key: str | None = None
    search_provider: str = "auto"

    ncbi_email: str | None = None
    ncbi_api_key: str | None = None

    database_url: str = "postgresql://postgres:postgres@localhost:5432/wmd_agent"
    qdrant_url: str = "http://localhost:6333"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "minio123"

    rag_default_top_k: int = Field(default=20, ge=1, le=100)
    rag_rerank_top_k: int = Field(default=8, ge=1, le=50)
    rag_confidence_threshold: float = Field(default=0.70, ge=0, le=1)

    request_timeout_seconds: float = Field(default=15.0, ge=3, le=60)
    demo_mode: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
