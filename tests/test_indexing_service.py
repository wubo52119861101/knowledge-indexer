import logging
from typing import Any

from app.connectors.base import BaseConnector
from app.core.minio import InMemoryObjectStorageRepository
from app.models.common import JobFailureStage, JobStatus, SourceType, SyncMode, generate_id
from app.models.document import Document
from app.models.source import Source
from app.repositories.checkpoint_repo import InMemoryCheckpointRepository
from app.repositories.chunk_repo import InMemoryChunkRepository
from app.repositories.document_repo import InMemoryDocumentRepository
from app.repositories.job_repo import InMemoryJobRepository
from app.repositories.source_repo import InMemorySourceRepository
from app.schemas.document import DocumentPayload
from app.services.document_processor import DocumentProcessor
from app.services.embedding_service import EmbeddingService, HashEmbeddingService
from app.services.indexing_service import IndexingService
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
            deleted=record.get("deleted", False),
            checkpoint_value=record.get("checkpoint_value"),
        )



def build_indexing_service(
    *,
    object_storage_repo: InMemoryObjectStorageRepository | None = None,
    embedding_service: EmbeddingService | None = None,
) -> tuple[
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
        embedding_service=embedding_service or HashEmbeddingService(dimension=16),
        object_storage_repo=object_storage_repo,
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
    assert result.failure_stage is JobFailureStage.NORMALIZE
    assert result.checkpoint_before == "10"
    assert result.checkpoint_after is None
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



def test_incremental_deleted_record_marks_document_deleted_and_clears_chunks() -> None:
    service, source_repo, document_repo, chunk_repo, checkpoint_repo, job_service = build_indexing_service()
    source = source_repo.add(
        Source(
            id="src_1",
            name="demo",
            type=SourceType.POSTGRES,
            config={"table": "knowledge_articles"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )
    existing_document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id=source.id,
            external_doc_id="doc-1",
            title="旧文档",
            content_text="旧内容",
            content_hash="old-hash",
            doc_type="faq",
            metadata={"updated_at": 10},
        )
    )
    chunk_repo.replace_for_document(existing_document.id, service._build_chunks(existing_document))
    checkpoint_repo.save(source.id, "default", "10|doc-0")

    job = job_service.create_job(source_id=source.id, mode=SyncMode.INCREMENTAL, triggered_by="tester")
    connector = StubConnector(
        [
            {
                "external_doc_id": "doc-1",
                "title": "旧文档",
                "content": "",
                "deleted": True,
                "checkpoint_value": "20|doc-1",
                "metadata": {"updated_at": 20, "deleted": True},
            }
        ]
    )

    result = service.run_job(source, job, connector)
    deleted_document = next(document for document in document_repo.list_all() if document.external_doc_id == "doc-1")

    assert result.status is JobStatus.SUCCEEDED
    assert result.checkpoint_after == "20|doc-1"
    assert checkpoint_repo.get(source.id, "default").checkpoint_value == "20|doc-1"
    assert deleted_document.status.value == "DELETED"
    assert chunk_repo.list_by_document(deleted_document.id) == []



def test_successful_job_archives_raw_snapshot() -> None:
    object_storage_repo = InMemoryObjectStorageRepository()
    service, source_repo, _document_repo, _chunk_repo, _checkpoint_repo, job_service = build_indexing_service(
        object_storage_repo=object_storage_repo
    )
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
    connector = StubConnector(
        [
            {
                "external_doc_id": "doc-1",
                "title": "文档 1",
                "content": "文档内容",
                "metadata": {"updated_at": 20},
            }
        ]
    )

    result = service.run_job(source, job, connector)

    assert result.status is JobStatus.SUCCEEDED
    assert result.snapshot_path == f"raw/{source.id}/{job.id}/records.jsonl.gz"
    assert result.snapshot_path in object_storage_repo.objects
    assert object_storage_repo.read_jsonl(result.snapshot_path)[0]["external_doc_id"] == "doc-1"



def test_failed_job_archives_failure_samples() -> None:
    object_storage_repo = InMemoryObjectStorageRepository()
    service, source_repo, _document_repo, _chunk_repo, checkpoint_repo, job_service = build_indexing_service(
        object_storage_repo=object_storage_repo
    )
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
        ]
    )

    result = service.run_job(source, job, connector)
    failed_records = object_storage_repo.read_jsonl(f"failed/{source.id}/{job.id}/records.jsonl.gz")

    assert result.status is JobStatus.FAILED
    assert result.snapshot_path == f"failed/{source.id}/{job.id}/records.jsonl.gz"
    assert f"raw/{source.id}/{job.id}/records.jsonl.gz" in object_storage_repo.objects
    assert failed_records[0]["stage"] == JobFailureStage.NORMALIZE.value
    assert failed_records[0]["error_message"] == "boom"



def test_sync_logs_include_structured_fields(caplog) -> None:
    service, source_repo, _document_repo, _chunk_repo, _checkpoint_repo, job_service = build_indexing_service()
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
    connector = StubConnector(
        [
            {
                "external_doc_id": "doc-1",
                "title": "文档 1",
                "content": "文档内容",
                "metadata": {"updated_at": 20},
            }
        ]
    )

    with caplog.at_level(logging.INFO):
        service.run_job(source, job, connector)

    finished_logs = [record.message for record in caplog.records if "sync_job_finished" in record.message]
    assert finished_logs
    assert f'job_id="{job.id}"' in finished_logs[0]
    assert 'source_id="src_1"' in finished_logs[0]
    assert 'mode="incremental"' in finished_logs[0]
    assert 'status="SUCCEEDED"' in finished_logs[0]
    assert "duration_ms=" in finished_logs[0]
