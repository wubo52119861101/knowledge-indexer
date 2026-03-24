from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.database import create_postgres_connection_factory
from app.core.minio import build_object_storage_repository
from app.flows.api_index_flow import ApiIndexFlow
from app.flows.file_index_flow import FileIndexFlow
from app.flows.postgres_index_flow import PostgresIndexFlow
from app.models.common import SourceType
from app.repositories.checkpoint_repo import InMemoryCheckpointRepository, PostgresCheckpointRepository
from app.repositories.chunk_repo import InMemoryChunkRepository, PostgresChunkRepository
from app.repositories.document_repo import InMemoryDocumentRepository, PostgresDocumentRepository
from app.repositories.job_repo import InMemoryJobRepository, PostgresJobRepository
from app.repositories.source_repo import InMemorySourceRepository, PostgresSourceRepository
from app.services.document_processor import DocumentProcessor
from app.services.embedding_service import build_embedding_service
from app.services.indexing_service import IndexingService
from app.services.job_service import JobService
from app.services.qa_service import QaService
from app.services.retrieval_service import RetrievalService
from app.services.source_service import SourceService
from app.services.sync_orchestrator import SyncOrchestrator, SyncWorker
from app.services.sync_queue import build_sync_queue


class ServiceContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._setup_repositories()
        self.sync_queue = build_sync_queue(settings)
        self.object_storage_repo = build_object_storage_repository(settings)

        self.document_processor = DocumentProcessor(
            chunk_size=settings.default_chunk_size,
            chunk_overlap=settings.default_chunk_overlap,
        )
        self.embedding_service = build_embedding_service(settings)
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
            object_storage_repo=self.object_storage_repo,
        )
        self.retrieval_service = RetrievalService(
            source_repo=self.source_repo,
            document_repo=self.document_repo,
            chunk_repo=self.chunk_repo,
            embedding_service=self.embedding_service,
            min_score_threshold=settings.search_score_threshold,
            candidate_multiplier=settings.retrieval_candidate_multiplier,
        )
        self.qa_service = QaService(settings=settings, retrieval_service=self.retrieval_service)

        self._flows = {
            SourceType.FILE: FileIndexFlow(self.indexing_service),
            SourceType.API: ApiIndexFlow(self.indexing_service, timeout_seconds=settings.api_connector_timeout_seconds),
            SourceType.POSTGRES: PostgresIndexFlow(self.indexing_service),
        }
        self.sync_orchestrator = SyncOrchestrator(
            settings=settings,
            source_service=self.source_service,
            checkpoint_repo=self.checkpoint_repo,
            job_service=self.job_service,
            sync_queue=self.sync_queue,
            flows=self._flows,
        )
        self.sync_worker = None
        if settings.sync_worker_enabled and not settings.sync_run_inline:
            self.sync_worker = SyncWorker(
                orchestrator=self.sync_orchestrator,
                poll_timeout_seconds=settings.sync_worker_poll_timeout_seconds,
            )

    def _setup_repositories(self) -> None:
        backend = self.settings.repository_backend.lower()
        if backend == "postgres":
            connection_factory = create_postgres_connection_factory(self.settings)
            self.source_repo = PostgresSourceRepository(connection_factory)
            self.document_repo = PostgresDocumentRepository(connection_factory)
            self.chunk_repo = PostgresChunkRepository(connection_factory)
            self.job_repo = PostgresJobRepository(connection_factory)
            self.checkpoint_repo = PostgresCheckpointRepository(connection_factory)
            return
        if backend != "inmemory":
            raise ValueError(f"unsupported repository backend: {self.settings.repository_backend}")

        self.source_repo = InMemorySourceRepository()
        self.document_repo = InMemoryDocumentRepository()
        self.chunk_repo = InMemoryChunkRepository()
        self.job_repo = InMemoryJobRepository()
        self.checkpoint_repo = InMemoryCheckpointRepository()

    def trigger_sync(self, source_id: str, mode, operator: str):
        return self.sync_orchestrator.trigger_sync(source_id=source_id, mode=mode, operator=operator)

    def start_background_workers(self) -> None:
        if self.sync_worker is not None:
            self.sync_worker.start()

    def shutdown_background_workers(self) -> None:
        if self.sync_worker is not None:
            self.sync_worker.stop()


@lru_cache(maxsize=1)
def get_container() -> ServiceContainer:
    return ServiceContainer(get_settings())
