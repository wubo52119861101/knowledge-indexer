from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector
from app.core.config import Settings
from app.models.common import JobStatus, SourceType, SyncMode
from app.models.job import IndexJob
from app.models.source import Source
from app.repositories.checkpoint_repo import InMemoryCheckpointRepository
from app.repositories.chunk_repo import InMemoryChunkRepository
from app.repositories.document_repo import InMemoryDocumentRepository
from app.repositories.job_repo import InMemoryJobRepository
from app.repositories.source_repo import InMemorySourceRepository
from app.schemas.document import DocumentPayload
from app.schemas.retrieval import AclContext, SearchFilters
from app.schemas.source import CreateSourceRequest
from app.services.document_processor import DocumentProcessor
from app.services.embedding_service import HashEmbeddingService
from app.services.indexing_service import IndexingService
from app.services.job_service import JobService
from app.services.qa_service import QaService
from app.services.retrieval_service import RetrievalService
from app.services.source_service import SourceService
from app.services.sync_orchestrator import SyncOrchestrator
from app.services.sync_queue import InMemorySyncQueue


class RegressionConnector(BaseConnector):
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.incremental_checkpoints: list[str | None] = []

    def test_connection(self, source: Source) -> bool:
        return True

    def pull_full(self, source: Source) -> list[Any]:
        return list(self.records)

    def pull_incremental(self, source: Source, checkpoint: str | None) -> list[Any]:
        self.incremental_checkpoints.append(checkpoint)
        return list(self.records)

    def normalize(self, source: Source, record: Any) -> DocumentPayload:
        return DocumentPayload(
            external_doc_id=record["external_doc_id"],
            title=record["title"],
            content=record["content"],
            doc_type=record.get("doc_type", "text"),
            metadata=dict(record.get("metadata") or {}),
            checkpoint_value=record.get("checkpoint_value"),
        )


class RegressionFlow:
    def __init__(self, indexing_service: IndexingService, connector: RegressionConnector) -> None:
        self.indexing_service = indexing_service
        self.connector = connector

    def run(self, source: Source, job: IndexJob) -> IndexJob:
        return self.indexing_service.run_job(source, job, self.connector)


def test_t7_end_to_end_sync_retrieval_and_qa_flow() -> None:
    source_repo = InMemorySourceRepository()
    document_repo = InMemoryDocumentRepository()
    chunk_repo = InMemoryChunkRepository()
    checkpoint_repo = InMemoryCheckpointRepository()
    job_service = JobService(InMemoryJobRepository())
    source_service = SourceService(source_repo)
    queue = InMemorySyncQueue(lock_ttl_seconds=60)
    embedding_service = HashEmbeddingService(dimension=32)
    indexing_service = IndexingService(
        source_repo=source_repo,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        checkpoint_repo=checkpoint_repo,
        job_service=job_service,
        document_processor=DocumentProcessor(chunk_size=120, chunk_overlap=20),
        embedding_service=embedding_service,
    )
    connector = RegressionConnector(
        records=[
            {
                "external_doc_id": "refund-1",
                "title": "退款规则",
                "content": "退款需要在七天内发起申请，系统会在三个工作日内原路退回。",
                "doc_type": "faq",
                "metadata": {"topic": "refund", "updated_at": 100},
                "checkpoint_value": "100",
            },
            {
                "external_doc_id": "invoice-1",
                "title": "发票说明",
                "content": "电子发票会在订单完成后自动发送到邮箱。",
                "doc_type": "guide",
                "metadata": {"topic": "invoice", "updated_at": 200},
                "checkpoint_value": "200",
            },
        ]
    )
    orchestrator = SyncOrchestrator(
        settings=Settings(app_env="test", sync_run_inline=False, sync_worker_enabled=False),
        source_service=source_service,
        checkpoint_repo=checkpoint_repo,
        job_service=job_service,
        sync_queue=queue,
        flows={SourceType.API: RegressionFlow(indexing_service, connector)},
    )
    retrieval_service = RetrievalService(
        source_repo=source_repo,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        embedding_service=embedding_service,
        min_score_threshold=0.05,
    )
    qa_service = QaService(
        settings=Settings(SEARCH_SCORE_THRESHOLD=0.05, MIN_EVIDENCE_COUNT=1),
        retrieval_service=retrieval_service,
    )

    source = source_service.create_source(
        CreateSourceRequest(
            name="售后知识库",
            type=SourceType.API,
            config={"base_url": "http://example.com"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )

    queued_job = orchestrator.trigger_sync(source.id, SyncMode.INCREMENTAL, "tester")
    assert queued_job.status is JobStatus.PENDING

    completed_job = orchestrator.process_next_job(timeout_seconds=0.0)

    assert completed_job is not None
    assert completed_job.id == queued_job.id
    assert completed_job.status is JobStatus.SUCCEEDED
    assert completed_job.processed_count == 2
    assert completed_job.failed_count == 0
    assert completed_job.checkpoint_after == "200"
    assert job_service.get_job(queued_job.id).status is JobStatus.SUCCEEDED
    assert connector.incremental_checkpoints == [None]
    assert checkpoint_repo.get(source.id, "default").checkpoint_value == "200"
    assert source_repo.get(source.id).last_sync_at is not None

    results = retrieval_service.search(
        query="退款需要在七天内发起申请，系统会在三个工作日内原路退回。",
        top_k=3,
        filters=SearchFilters(
            source_ids=[source.id],
            doc_types=["faq"],
            metadata={"topic": "refund"},
        ),
        acl_context=AclContext(),
    )

    assert len(document_repo.list_all()) == 2
    assert len(results) == 1
    assert results[0].document.title == "退款规则"
    assert results[0].source.source_id == source.id

    answer = qa_service.ask(
        question="退款需要在七天内发起申请，系统会在三个工作日内原路退回。",
        top_k=3,
        filters=SearchFilters(source_ids=[source.id]),
        acl_context=AclContext(),
    )

    assert answer.evidence_status.value == "SUFFICIENT"
    assert "根据知识库检索结果" in answer.answer
    assert len(answer.citations) >= 1
    assert answer.citations[0].document.title == "退款规则"
