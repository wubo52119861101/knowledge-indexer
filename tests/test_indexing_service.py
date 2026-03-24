from threading import Event
from typing import Any

from app.connectors.base import BaseConnector
from app.core.config import Settings
from app.models.common import JobStatus, SourceType, SyncMode, generate_id
from app.models.document import Document
from app.models.job import IndexJob
from app.models.source import Source
from app.repositories.checkpoint_repo import InMemoryCheckpointRepository
from app.repositories.chunk_repo import InMemoryChunkRepository
from app.repositories.document_repo import InMemoryDocumentRepository
from app.repositories.job_repo import InMemoryJobRepository
from app.repositories.source_repo import InMemorySourceRepository
from app.schemas.document import DocumentPayload
from app.services.document_processor import DocumentProcessor
from app.services.embedding_service import HashEmbeddingService
from app.services.indexing_service import IndexingService
from app.services.job_runner import JobRunner
from app.services.job_service import JobService


class StubConnector(BaseConnector):
    def __init__(self, records: list[Any]) -> None:
        self.records = records

    def test_connection(self, source: Source) -> bool:
        return True

    def pull_full(self, source: Source) -> list[Any]:
        return list(self.records)

    def pull_incremental(self, source: Source, checkpoint: str | None) -> list[Any]:
        return list(self.records)

    def normalize(self, source: Source, record: Any) -> DocumentPayload:
        if record.get("raise_error"):
            raise ValueError(record["raise_error"])
        return DocumentPayload(
            external_doc_id=record["external_doc_id"],
            title=record["title"],
            content=record["content"],
            doc_type=record.get("doc_type", "text"),
            metadata=dict(record.get("metadata") or {}),
            acl=[],
        )


def build_indexing_service() -> tuple[
    IndexingService,
    InMemorySourceRepository,
    InMemoryDocumentRepository,
    InMemoryChunkRepository,
    InMemoryCheckpointRepository,
    JobService,
]:
    source_repo = InMemorySourceRepository()
    document_repo = InMemoryDocumentRepository()
    chunk_repo = InMemoryChunkRepository()
    checkpoint_repo = InMemoryCheckpointRepository()
    job_repo = InMemoryJobRepository()
    job_service = JobService(job_repo)
    service = IndexingService(
        source_repo=source_repo,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        checkpoint_repo=checkpoint_repo,
        job_service=job_service,
        document_processor=DocumentProcessor(chunk_size=50, chunk_overlap=10),
        embedding_service=HashEmbeddingService(dimension=16),
    )
    return service, source_repo, document_repo, chunk_repo, checkpoint_repo, job_service


def test_incremental_failure_does_not_advance_checkpoint() -> None:
    service, source_repo, document_repo, _chunk_repo, checkpoint_repo, job_service = build_indexing_service()
    source = source_repo.add(
        Source(
            id="src_1",
            name="demo",
            type=SourceType.API,
            config={"base_url": "http://example.com"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )
    checkpoint_repo.save(source.id, "default", "10")
    job = job_service.create_job(source_id=source.id, mode=SyncMode.INCREMENTAL, triggered_by="tester")
    connector = StubConnector(
        [
            {"external_doc_id": "doc-1", "title": "bad", "content": "bad", "raise_error": "boom"},
            {
                "external_doc_id": "doc-2",
                "title": "good",
                "content": "good content",
                "metadata": {"updated_at": 20},
            },
        ]
    )

    result = service.run_job(source, job, connector)

    assert result.status is JobStatus.FAILED
    assert result.failed_count == 1
    assert checkpoint_repo.get(source.id, "default").checkpoint_value == "10"
    assert len(document_repo.list_all()) == 1


def test_full_sync_marks_missing_documents_deleted_and_clears_chunks() -> None:
    service, source_repo, document_repo, chunk_repo, _checkpoint_repo, job_service = build_indexing_service()
    source = source_repo.add(
        Source(
            id="src_1",
            name="demo",
            type=SourceType.FILE,
            config={"root_path": "/tmp"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )
    stale_document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id=source.id,
            external_doc_id="stale-doc",
            title="旧文档",
            content_text="旧内容",
            content_hash="old-hash",
            doc_type="faq",
            metadata={},
        )
    )
    chunk_repo.replace_for_document(
        stale_document.id,
        service._build_chunks(stale_document),
    )

    job = job_service.create_job(source_id=source.id, mode=SyncMode.FULL, triggered_by="tester")
    connector = StubConnector(
        [
            {
                "external_doc_id": "fresh-doc",
                "title": "新文档",
                "content": "新的规则说明",
                "metadata": {"updated_at": 30},
            }
        ]
    )

    result = service.run_job(source, job, connector)
    stale_after_sync = next(document for document in document_repo.list_all() if document.external_doc_id == "stale-doc")
    fresh_after_sync = next(document for document in document_repo.list_all() if document.external_doc_id == "fresh-doc")

    assert result.status is JobStatus.SUCCEEDED
    assert stale_after_sync.status.value == "DELETED"
    assert chunk_repo.list_by_document(stale_after_sync.id) == []
    assert fresh_after_sync.status.value == "ACTIVE"
    assert chunk_repo.list_by_document(fresh_after_sync.id) != []


class BlockingConnector(StubConnector):
    def __init__(self, records: list[Any], first_record_started: Event, resume_first_record: Event) -> None:
        super().__init__(records)
        self.first_record_started = first_record_started
        self.resume_first_record = resume_first_record
        self.normalize_calls = 0

    def normalize(self, source: Source, record: Any) -> DocumentPayload:
        payload = super().normalize(source, record)
        if self.normalize_calls == 0:
            self.first_record_started.set()
            self.resume_first_record.wait(timeout=2)
        self.normalize_calls += 1
        return payload


def test_background_runner_cancels_running_job_without_checkpoint_or_touch_sync() -> None:
    service, source_repo, _document_repo, _chunk_repo, checkpoint_repo, job_service = build_indexing_service()
    source = source_repo.add(
        Source(
            id="src_1",
            name="demo",
            type=SourceType.API,
            config={"base_url": "http://example.com"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )
    job = job_service.create_job(source_id=source.id, mode=SyncMode.INCREMENTAL, triggered_by="tester")
    first_record_started = Event()
    resume_first_record = Event()
    connector = BlockingConnector(
        [
            {"external_doc_id": "doc-1", "title": "one", "content": "first"},
            {"external_doc_id": "doc-2", "title": "two", "content": "second"},
        ],
        first_record_started=first_record_started,
        resume_first_record=resume_first_record,
    )
    runner = JobRunner(Settings(SYNC_RUN_INLINE=False))

    queued_job = runner.submit(job, lambda: service.run_job(source, job, connector))

    assert queued_job.status in {JobStatus.PENDING, JobStatus.RUNNING}
    assert first_record_started.wait(timeout=2) is True

    cancelling = job_service.request_cancel(job.id, operator="system", reason="manual cancel")
    assert cancelling.status is JobStatus.CANCELLING

    resume_first_record.set()
    assert runner.wait(job.id, timeout=2) is True

    result = job_service.get_job(job.id)
    assert result is not None
    assert result.status is JobStatus.CANCELLED
    assert result.cancel_requested_by == "system"
    assert result.cancel_reason == "manual cancel"
    assert checkpoint_repo.get(source.id, "default") is None
    assert source_repo.get(source.id).last_sync_at is None
