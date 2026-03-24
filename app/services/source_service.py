from __future__ import annotations

from app.connectors.postgres_connector import PostgresConnector
from app.models.common import SourceType, generate_id
from app.models.source import Source
from app.repositories.source_repo import SourceRepository
from app.schemas.source import CreateSourceRequest


class SourceService:
    def __init__(
        self,
        source_repo: SourceRepository,
        *,
        postgres_connector: PostgresConnector | None = None,
    ) -> None:
        self.source_repo = source_repo
        self.postgres_connector = postgres_connector or PostgresConnector()

    def create_source(self, request: CreateSourceRequest) -> Source:
        if request.type is SourceType.FILE and not request.config.get("root_path"):
            raise ValueError("file source requires config.root_path")
        if request.type is SourceType.API and not request.config.get("base_url"):
            raise ValueError("api source requires config.base_url")

        source = Source(
            id=generate_id("src"),
            name=request.name,
            type=request.type,
            config=request.config,
            sync_mode=request.sync_mode,
            enabled=request.enabled,
        )
        self._validate_source(source)
        return self.source_repo.add(source)

    def get_source(self, source_id: str) -> Source | None:
        return self.source_repo.get(source_id)

    def _validate_source(self, source: Source) -> None:
        if source.type is not SourceType.POSTGRES:
            return
        try:
            self.postgres_connector.test_connection(source)
        except Exception as exc:
            raise ValueError(f"postgres source validation failed: {exc}") from exc
