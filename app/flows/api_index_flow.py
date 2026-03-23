from __future__ import annotations

from app.connectors.custom_api_connector import ApiConnector
from app.models.job import IndexJob
from app.models.source import Source
from app.services.indexing_service import IndexingService


class ApiIndexFlow:
    def __init__(self, indexing_service: IndexingService, timeout_seconds: float) -> None:
        self.indexing_service = indexing_service
        self.connector = ApiConnector(timeout_seconds=timeout_seconds)

    def run(self, source: Source, job: IndexJob) -> IndexJob:
        return self.indexing_service.run_job(source, job, self.connector)
