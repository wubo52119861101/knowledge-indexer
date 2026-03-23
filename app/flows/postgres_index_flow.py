from __future__ import annotations

from app.connectors.postgres_connector import PostgresConnector
from app.models.job import IndexJob
from app.models.source import Source
from app.services.indexing_service import IndexingService


class PostgresIndexFlow:
    def __init__(self, indexing_service: IndexingService) -> None:
        self.indexing_service = indexing_service
        self.connector = PostgresConnector()

    def run(self, source: Source, job: IndexJob) -> IndexJob:
        return self.indexing_service.run_job(source, job, self.connector)
