from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.connectors.base import BaseConnector
from app.core.logger import get_logger, log_event
from app.core.minio import DisabledObjectStorageRepository, ObjectStorageRepository
from app.models.chunk import Chunk
from app.models.common import AclEffect, AclType, DocumentStatus, EmbeddingStatus, JobFailureStage, SyncMode, generate_id, utcnow
from app.models.document import Document, DocumentAcl
from app.models.job import IndexJob
from app.models.source import Source
from app.repositories.checkpoint_repo import CheckpointRepository
from app.repositories.chunk_repo import ChunkRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.source_repo import SourceRepository
from app.services.document_processor import DocumentProcessor
from app.services.embedding_service import EmbeddingService
from app.services.job_service import JobService


logger = get_logger(__name__)


class IndexingService:
    def __init__(
        self,
        source_repo: SourceRepository,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        checkpoint_repo: CheckpointRepository,
        job_service: JobService,
        document_processor: DocumentProcessor,
        embedding_service: EmbeddingService,
        object_storage_repo: ObjectStorageRepository | None = None,
    ) -> None:
        self.source_repo = source_repo
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.checkpoint_repo = checkpoint_repo
        self.job_service = job_service
        self.document_processor = document_processor
        self.embedding_service = embedding_service
        self.object_storage_repo = object_storage_repo or DisabledObjectStorageRepository()

    def run_job(self, source: Source, job: IndexJob, connector: BaseConnector) -> IndexJob:
        checkpoint = self.checkpoint_repo.get(source.id, "default")
        checkpoint_before = checkpoint.checkpoint_value if checkpoint else None
        if job.checkpoint_before != checkpoint_before:
            job.checkpoint_before = checkpoint_before
            self.job_service.save(job)

        self.job_service.mark_running(job)
        self._log_job_started(job)
        is_full_snapshot = job.mode in {SyncMode.FULL, SyncMode.REBUILD}
        raw_records: list[Any] = []
        failure_samples: list[dict[str, Any]] = []

        try:
            raw_records = self._pull_records(
                source=source,
                connector=connector,
                is_full_snapshot=is_full_snapshot,
                checkpoint_before=checkpoint_before,
            )
            raw_snapshot_path = self._archive_raw_records(source.id, job.id, raw_records)
            if raw_snapshot_path is not None:
                self.job_service.set_snapshot_path(job, raw_snapshot_path)

            processed_count = 0
            failed_count = 0
            latest_checkpoint = checkpoint_before
            seen_external_doc_ids: set[str] = set()
            error_messages: list[str] = []
            last_failure_stage: JobFailureStage | None = None

            for raw_record in raw_records:
                try:
                    payload = connector.normalize(source, raw_record)
                except Exception as exc:
                    failed_count += 1
                    last_failure_stage = JobFailureStage.NORMALIZE
                    error_messages.append(str(exc))
                    failure_samples.append(
                        self._build_failure_sample(
                            stage=JobFailureStage.NORMALIZE,
                            raw_record=raw_record,
                            error=exc,
                        )
                    )
                    self.job_service.update_progress(job, processed_count=processed_count, failed_count=failed_count)
                    continue

                try:
                    seen_external_doc_ids.add(payload.external_doc_id)
                    document = self._persist_document(source, payload)
                    if payload.deleted:
                        self.chunk_repo.replace_for_document(document.id, [])
                    else:
                        chunks = self._build_chunks(document)
                        self.chunk_repo.replace_for_document(document.id, chunks)
                    processed_count += 1
                    latest_checkpoint = self._next_checkpoint(latest_checkpoint, payload)
                    self.job_service.update_progress(
                        job,
                        processed_count=processed_count,
                        failed_count=failed_count,
                        checkpoint_after=str(latest_checkpoint) if latest_checkpoint is not None else None,
                    )
                except Exception as exc:
                    failed_count += 1
                    last_failure_stage = self._failure_stage_for_exception(exc)
                    error_messages.append(str(exc))
                    failure_samples.append(
                        self._build_failure_sample(
                            stage=last_failure_stage,
                            raw_record=raw_record,
                            payload=payload.model_dump(mode="json"),
                            error=exc,
                        )
                    )
                    self.job_service.update_progress(job, processed_count=processed_count, failed_count=failed_count)

            if failed_count > 0:
                summary = "; ".join(error_messages[:3]) if error_messages else "record processing failed"
                failed_snapshot_path = self._archive_failed_records(source.id, job.id, failure_samples)
                if failed_snapshot_path is not None:
                    self.job_service.set_snapshot_path(job, failed_snapshot_path)
                result = self.job_service.mark_failed(
                    job,
                    error_summary=f"{failed_count} record(s) failed: {summary}",
                    failed_count=failed_count,
                    failure_stage=last_failure_stage,
                )
                self._log_job_finished(result)
                return result

            self._finalize_snapshot(source.id, is_full_snapshot, seen_external_doc_ids)
            if latest_checkpoint is not None:
                self.checkpoint_repo.save(source.id, "default", str(latest_checkpoint))
            self.source_repo.touch_sync(source.id)
            result = self.job_service.mark_succeeded(
                job,
                processed_count=processed_count,
                failed_count=failed_count,
                checkpoint_after=str(latest_checkpoint) if latest_checkpoint is not None else None,
            )
            self._log_job_finished(result)
            return result
        except Exception as exc:
            failure_samples.append(
                self._build_failure_sample(
                    stage=JobFailureStage.PULL,
                    error=exc,
                    raw_record={"record_count": len(raw_records)},
                )
            )
            failed_snapshot_path = self._archive_failed_records(source.id, job.id, failure_samples)
            if failed_snapshot_path is not None:
                self.job_service.set_snapshot_path(job, failed_snapshot_path)
            result = self.job_service.mark_failed(
                job,
                error_summary=str(exc),
                failed_count=job.failed_count,
                failure_stage=JobFailureStage.PULL,
            )
            self._log_job_finished(result)
            return result

    def _pull_records(
        self,
        *,
        source: Source,
        connector: BaseConnector,
        is_full_snapshot: bool,
        checkpoint_before: str | None,
    ) -> list[Any]:
        if is_full_snapshot:
            return connector.pull_full(source)
        return connector.pull_incremental(source, checkpoint_before)

    def _persist_document(self, source: Source, payload) -> Document:
        cleaned_text = self.document_processor.clean_text(payload.content)
        content_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()
        return self.document_repo.upsert(
            Document(
                id=generate_id("doc"),
                source_id=source.id,
                external_doc_id=payload.external_doc_id,
                title=payload.title,
                content_text=cleaned_text,
                content_hash=content_hash,
                doc_type=payload.doc_type,
                metadata=payload.metadata,
                status=DocumentStatus.DELETED if payload.deleted else DocumentStatus.ACTIVE,
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

    def _finalize_snapshot(self, source_id: str, is_full_snapshot: bool, seen_external_doc_ids: set[str]) -> None:
        if not is_full_snapshot:
            return

        removed_documents = self.document_repo.mark_missing_as_deleted(source_id, seen_external_doc_ids)
        for document in removed_documents:
            self.chunk_repo.replace_for_document(document.id, [])

    def _build_chunks(self, document: Document) -> list[Chunk]:
        chunks: list[Chunk] = []
        for chunk_index, chunk_text in enumerate(self.document_processor.split_text(document.content_text)):
            try:
                embedding = self.embedding_service.embed(chunk_text)
            except Exception as exc:
                raise RuntimeError(str(exc)) from EmbeddingStageError(str(exc))

            chunks.append(
                Chunk(
                    id=generate_id("chk"),
                    document_id=document.id,
                    chunk_index=chunk_index,
                    content=chunk_text,
                    summary=self.document_processor.summarize(chunk_text),
                    token_count=self.document_processor.estimate_token_count(chunk_text),
                    metadata={**document.metadata, "source_id": document.source_id, "doc_type": document.doc_type},
                    embedding=embedding,
                    embedding_status=EmbeddingStatus.DONE,
                )
            )
        return chunks

    def _failure_stage_for_exception(self, exc: Exception) -> JobFailureStage:
        if exc.__cause__ is not None and isinstance(exc.__cause__, EmbeddingStageError):
            return JobFailureStage.EMBED
        return JobFailureStage.PERSIST

    def _next_checkpoint(self, current_value: str | float | int | None, payload) -> str | float | int | None:
        if getattr(payload, "checkpoint_value", None) is not None:
            return payload.checkpoint_value
        return self._max_checkpoint(
            current_value,
            payload.metadata.get("updated_at") or utcnow().timestamp(),
        )

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

    def _archive_raw_records(self, source_id: str, job_id: str, raw_records: list[Any]) -> str | None:
        return self._archive_records(
            object_name=f"raw/{source_id}/{job_id}/records.jsonl.gz",
            records=raw_records,
            archive_kind="raw",
            source_id=source_id,
            job_id=job_id,
        )

    def _archive_failed_records(self, source_id: str, job_id: str, failed_records: list[dict[str, Any]]) -> str | None:
        if not failed_records:
            return None
        return self._archive_records(
            object_name=f"failed/{source_id}/{job_id}/records.jsonl.gz",
            records=failed_records,
            archive_kind="failed",
            source_id=source_id,
            job_id=job_id,
        )

    def _archive_records(
        self,
        *,
        object_name: str,
        records: list[Any],
        archive_kind: str,
        source_id: str,
        job_id: str,
    ) -> str | None:
        try:
            return self.object_storage_repo.upload_jsonl_gz(object_name, records)
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "sync_archive_failed",
                archive_kind=archive_kind,
                error=str(exc),
                job_id=job_id,
                record_count=len(records),
                source_id=source_id,
            )
            return None

    def _build_failure_sample(
        self,
        *,
        stage: JobFailureStage,
        error: Exception,
        raw_record: Any | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sample: dict[str, Any] = {
            "stage": stage.value,
            "error_type": error.__class__.__name__,
            "error_message": str(error),
            "occurred_at": utcnow().isoformat(),
        }
        if raw_record is not None:
            sample["raw_record"] = raw_record
        if payload is not None:
            sample["payload"] = payload
        return sample

    def _log_job_started(self, job: IndexJob) -> None:
        log_event(
            logger,
            logging.INFO,
            "sync_job_started",
            checkpoint_before=job.checkpoint_before,
            job_id=job.id,
            mode=job.mode.value,
            source_id=job.source_id,
            status=job.status.value,
        )

    def _log_job_finished(self, job: IndexJob) -> None:
        level = logging.INFO if job.status.value == "SUCCEEDED" else logging.WARNING
        log_event(
            logger,
            level,
            "sync_job_finished",
            duration_ms=self._duration_ms(job),
            failed_count=job.failed_count,
            failure_stage=job.failure_stage.value if job.failure_stage else None,
            job_id=job.id,
            mode=job.mode.value,
            processed_count=job.processed_count,
            snapshot_path=job.snapshot_path,
            source_id=job.source_id,
            status=job.status.value,
        )

    def _duration_ms(self, job: IndexJob) -> int | None:
        if job.started_at is None or job.finished_at is None:
            return None
        return max(int((job.finished_at - job.started_at).total_seconds() * 1000), 0)


class EmbeddingStageError(RuntimeError):
    pass
