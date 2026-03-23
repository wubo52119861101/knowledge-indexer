from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="knowledge-indexer", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    internal_api_token: str | None = Field(default=None, alias="INTERNAL_API_TOKEN")
    default_chunk_size: int = Field(default=600, alias="DEFAULT_CHUNK_SIZE")
    default_chunk_overlap: int = Field(default=80, alias="DEFAULT_CHUNK_OVERLAP")
    embedding_dimension: int = Field(default=64, alias="EMBEDDING_DIMENSION")
    search_score_threshold: float = Field(default=0.12, alias="SEARCH_SCORE_THRESHOLD")
    min_evidence_count: int = Field(default=1, alias="MIN_EVIDENCE_COUNT")
    sync_run_inline: bool = Field(default=True, alias="SYNC_RUN_INLINE")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    minio_endpoint: str | None = Field(default=None, alias="MINIO_ENDPOINT")
    minio_access_key: str | None = Field(default=None, alias="MINIO_ACCESS_KEY")
    minio_secret_key: str | None = Field(default=None, alias="MINIO_SECRET_KEY")
    minio_bucket: str | None = Field(default=None, alias="MINIO_BUCKET")
    api_connector_timeout_seconds: float = Field(default=10.0, alias="API_CONNECTOR_TIMEOUT_SECONDS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
