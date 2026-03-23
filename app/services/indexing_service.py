from __future__ import annotations

import hashlib
from typing import Any

from app.connectors.base import BaseConnector
from app.models.chunk import Chunk
from app.models.common import AclEffect, AclType, EmbeddingStatus, SyncMode, generate_id, utcnow
from app.models.document import Document, DocumentAcl
from app.models.job import IndexJob
from app.models.source import Source
from app.repositories.checkpoint_repo import CheckpointRepository
from app.repositories.chunk_repo import ChunkRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.source_repo import SourceRepository
from app.services.document_processor import DocumentProcessor
from app.services.embedding_service import HashEmbeddingService
from app.services.job_service import JobService


class IndexingService:
    def __init__(
        self,
        source_repo: SourceRepository,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        checkpoint_repo: CheckpointRepository,
        job_service: JobService,
        document_processor: DocumentProcessor,
        embedding_service: HashEmbeddingService,
    ) -> None:
        self.source_repo = source_repo
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.checkpoint_repo = checkpoint_repo
        self.job_service = job_service
        self.document_processor = document_processor
        self.embedding_service = embedding_service

    def run_job(self, source: Source, job: IndexJob, connector: BaseConnector) -> IndexJob:
        self.job_service.mark_running(job)
        checkpoint = self.checkpoint_repo.get(source.id, "default")
        is_full_snapshot = job.mode in {SyncMode.FULL, SyncMode.REBUILD}

        try:
            raw_records = (
                connector.pull_full(source)
                if is_full_snapshot
                else connector.pull_incremental(source, checkpoint.checkpoint_value if checkpoint else None)
            )
            processed_count = 0
            failed_count = 0
            latest_checkpoint = checkpoint.checkpoint_value if checkpoint else None
            seen_external_doc_ids: set[str] = set()
            error_messages: list[str] = []

            for raw_record in raw_records:
                try:
                    payload = connector.normalize(source, raw_record)
                    seen_external_doc_ids.add(payload.external_doc_id)
                    cleaned_text = self.document_processor.clean_text(payload.content)
                    content_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()
                    document = self.document_repo.upsert(
                        Document(
                            id=generate_id("doc"),
                            source_id=source.id,
                            external_doc_id=payload.external_doc_id,
                            title=payload.title,
                            content_text=cleaned_text,
                            content_hash=content_hash,
                            doc_type=payload.doc_type,
                            metadata=payload.metadata,
                            acl_entries=[
                                DocumentAcl(
                                    acl_type=AclType(acl_item.type),
                                    acl_value=acl_item.value,
                                    effect=AclEffect(acl_item.effect),
                                )
                                for acl_item in payload.acl
                            ],
                        )
                    )
                    chunks = self._build_chunks(document)
                    self.chunk_repo.replace_for_document(document.id, chunks)
                    processed_count += 1
                    latest_checkpoint = self._max_checkpoint(
                        latest_checkpoint,
                        payload.metadata.get("updated_at") or utcnow().timestamp(),
                    )
                except Exception as exc:
                    failed_count += 1
                    error_messages.append(str(exc))

            if failed_count > 0:
                summary = "; ".join(error_messages[:3]) if error_messages else "record processing failed"
                return self.job_service.mark_failed(
                    job,
                    error_summary=f"{failed_count} record(s) failed: {summary}",
                    failed_count=failed_count,
                )

            if is_full_snapshot:
                removed_documents = self.document_repo.mark_missing_as_deleted(source.id, seen_external_doc_ids)
                for document in removed_documents:
                    self.chunk_repo.replace_for_document(document.id, [])

            if latest_checkpoint is not None:
                self.checkpoint_repo.save(source.id, "default", str(latest_checkpoint))
            self.source_repo.touch_sync(source.id)
            return self.job_service.mark_succeeded(job, processed_count=processed_count, failed_count=failed_count)
        except Exception as exc:
            return self.job_service.mark_failed(job, error_summary=str(exc), failed_count=job.failed_count)

    def _build_chunks(self, document: Document) -> list[Chunk]:
        chunks: list[Chunk] = []
        for chunk_index, chunk_text in enumerate(self.document_processor.split_text(document.content_text)):
            chunks.append(
                Chunk(
                    id=generate_id("chk"),
                    document_id=document.id,
                    chunk_index=chunk_index,
                    content=chunk_text,
                    summary=self.document_processor.summarize(chunk_text),
                    token_count=self.document_processor.estimate_token_count(chunk_text),
                    metadata={"source_id": document.source_id, "doc_type": document.doc_type},
                    embedding=self.embedding_service.embed(chunk_text),
                    embedding_status=EmbeddingStatus.DONE,
                )
            )
        return chunks

    def _max_checkpoint(self, current_value: str | float | int | None, candidate_value: Any) -> str | float | int | None:
        if candidate_value is None:
            return current_value
        if current_value is None:
            return candidate_value

        current_number = self._to_float(current_value)
        candidate_number = self._to_float(candidate_value)
        if current_number is not None and candidate_number is not None:
            return candidate_value if candidate_number >= current_number else current_value
        return str(candidate_value) if str(candidate_value) >= str(current_value) else current_value

    def _to_float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
