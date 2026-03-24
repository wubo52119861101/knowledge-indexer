from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models.common import JobRunnerMode, PipelineEngineType


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

    llm_enabled: bool = Field(default=False, alias="LLM_ENABLED")
    llm_provider: str = Field(default="http", alias="LLM_PROVIDER")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_model: str | None = Field(default=None, alias="LLM_MODEL")
    llm_timeout_seconds: float = Field(default=8.0, alias="LLM_TIMEOUT_SECONDS")
    ask_evidence_top_n: int = Field(default=3, alias="ASK_EVIDENCE_TOP_N")
    ask_max_context_chars: int = Field(default=4000, alias="ASK_MAX_CONTEXT_CHARS")

    rerank_enabled: bool = Field(default=False, alias="RERANK_ENABLED")
    rerank_provider: str = Field(default="http", alias="RERANK_PROVIDER")
    rerank_base_url: str | None = Field(default=None, alias="RERANK_BASE_URL")
    rerank_api_key: str | None = Field(default=None, alias="RERANK_API_KEY")
    rerank_timeout_seconds: float = Field(default=3.0, alias="RERANK_TIMEOUT_SECONDS")
    rerank_top_n: int = Field(default=10, alias="RERANK_TOP_N")

    pipeline_engine_type: PipelineEngineType = Field(default=PipelineEngineType.BUILTIN, alias="PIPELINE_ENGINE_TYPE")
    pipeline_engine_name: str = Field(default="knowledge-indexer", alias="PIPELINE_ENGINE_NAME")
    job_runner_mode: JobRunnerMode | None = Field(default=None, alias="JOB_RUNNER_MODE")

    @property
    def resolved_job_runner_mode(self) -> JobRunnerMode:
        if self.job_runner_mode is not None:
            return self.job_runner_mode
        return JobRunnerMode.INLINE if self.sync_run_inline else JobRunnerMode.BACKGROUND


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
