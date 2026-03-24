from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.flows.api_index_flow import ApiIndexFlow
from app.flows.file_index_flow import FileIndexFlow
from app.flows.postgres_index_flow import PostgresIndexFlow
from app.models.common import SourceType, SyncMode
from app.repositories.checkpoint_repo import InMemoryCheckpointRepository
from app.repositories.chunk_repo import InMemoryChunkRepository
from app.repositories.document_repo import InMemoryDocumentRepository
from app.repositories.job_repo import InMemoryJobRepository
from app.repositories.source_repo import InMemorySourceRepository
from app.services.answer_generator import NoopAnswerGenerator
from app.services.document_processor import DocumentProcessor
from app.services.embedding_service import HashEmbeddingService
from app.services.indexing_service import IndexingService
from app.services.job_runner import JobRunner
from app.services.job_service import JobService
from app.services.pipeline_engine_service import PipelineEngineService
from app.services.qa_service import QaService
from app.services.rerank_service import NoopRerankService
from app.services.retrieval_service import RetrievalService
from app.services.source_service import SourceService


class ServiceContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.source_repo = InMemorySourceRepository()
        self.document_repo = InMemoryDocumentRepository()
        self.chunk_repo = InMemoryChunkRepository()
        self.job_repo = InMemoryJobRepository()
        self.checkpoint_repo = InMemoryCheckpointRepository()

        self.document_processor = DocumentProcessor(
            chunk_size=settings.default_chunk_size,
            chunk_overlap=settings.default_chunk_overlap,
        )
        self.embedding_service = HashEmbeddingService(dimension=settings.embedding_dimension)
        self.pipeline_engine_service = PipelineEngineService(settings)
        self.answer_generator = NoopAnswerGenerator(settings)
        self.rerank_service = NoopRerankService(settings)
        self.job_runner = JobRunner(settings)
        self.job_service = JobService(self.job_repo)
        self.source_service = SourceService(self.source_repo)
        self.indexing_service = IndexingService(
            source_repo=self.source_repo,
            document_repo=self.document_repo,
            chunk_repo=self.chunk_repo,
            checkpoint_repo=self.checkpoint_repo,
            job_service=self.job_service,
            document_processor=self.document_processor,
            embedding_service=self.embedding_service,
        )
        self.retrieval_service = RetrievalService(
            source_repo=self.source_repo,
            document_repo=self.document_repo,
            chunk_repo=self.chunk_repo,
            embedding_service=self.embedding_service,
            min_score_threshold=settings.search_score_threshold,
        )
        self.qa_service = QaService(
            settings=settings,
            retrieval_service=self.retrieval_service,
            answer_generator=self.answer_generator,
            rerank_service=self.rerank_service,
            pipeline_engine_service=self.pipeline_engine_service,
        )

        self._flows = {
            SourceType.FILE: FileIndexFlow(self.indexing_service),
            SourceType.API: ApiIndexFlow(self.indexing_service, timeout_seconds=settings.api_connector_timeout_seconds),
            SourceType.POSTGRES: PostgresIndexFlow(self.indexing_service),
        }

    def trigger_sync(self, source_id: str, mode: SyncMode, operator: str):
        source = self.source_service.get_source(source_id)
        if source is None:
            raise KeyError(f"source {source_id} not found")
        if not source.enabled:
            raise ValueError(f"source {source_id} is disabled")

        flow = self._flows[source.type]
        job = self.job_service.create_job(
            source_id=source_id,
            mode=mode,
            triggered_by=operator,
            pipeline_engine=self.pipeline_engine_service.resolve_for_job(
                self.pipeline_engine_service.describe_builtin_flow(flow)
            ),
        )
        return self.job_runner.submit(job, lambda: flow.run(source, job))


@lru_cache(maxsize=1)
def get_container() -> ServiceContainer:
    return ServiceContainer(get_settings())
