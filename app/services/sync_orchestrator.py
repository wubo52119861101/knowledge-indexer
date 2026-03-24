from __future__ import annotations

from threading import Event, Thread
from time import sleep
from typing import Any

from app.core.config import Settings
from app.core.logger import get_logger
from app.models.common import JobFailureStage, JobStatus, SyncMode, generate_id
from app.models.job import IndexJob
from app.models.source import Source
from app.repositories.checkpoint_repo import CheckpointRepository
from app.services.job_service import JobService
from app.services.source_service import SourceService
from app.services.sync_queue import SyncQueue, SyncQueueMessage

logger = get_logger(__name__)


class SyncOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        source_service: SourceService,
        checkpoint_repo: CheckpointRepository,
        job_service: JobService,
        sync_queue: SyncQueue,
        flows: dict[Any, Any],
    ) -> None:
        self.settings = settings
        self.source_service = source_service
        self.checkpoint_repo = checkpoint_repo
        self.job_service = job_service
        self.sync_queue = sync_queue
        self.flows = flows

    def trigger_sync(self, source_id: str, mode: SyncMode, operator: str) -> IndexJob:
        source = self.source_service.get_source(source_id)
        if source is None:
            raise KeyError(f"source {source_id} not found")
        if not source.enabled:
            raise ValueError(f"source {source_id} is disabled")

        active_job = self.job_service.get_active_job_for_source(source_id)
        if active_job is not None:
            raise ValueError(f"source {source_id} already has active job {active_job.id}")

        job_id = generate_id("job")
        if not self.sync_queue.acquire_source_lock(source_id, job_id):
            lock_owner = self.sync_queue.get_source_lock_owner(source_id)
            raise ValueError(f"source {source_id} already has active job {lock_owner or 'unknown'}")

        checkpoint = self.checkpoint_repo.get(source_id, "default")
        checkpoint_before = checkpoint.checkpoint_value if checkpoint else None
        job: IndexJob | None = None
        try:
            job = self.job_service.create_job(
                source_id=source_id,
                mode=mode,
                triggered_by=operator,
                job_id=job_id,
                checkpoint_before=checkpoint_before,
            )
            if self.settings.sync_run_inline:
                return self.process_job(job.id)

            self.sync_queue.enqueue(SyncQueueMessage(job_id=job.id, source_id=source_id))
            return job
        except Exception:
            self.sync_queue.release_source_lock(source_id, job_id)
            if job is not None:
                self.job_service.mark_failed(
                    job,
                    error_summary="failed to enqueue sync job",
                    failure_stage=JobFailureStage.QUEUE,
                )
            raise

    def process_next_job(self, timeout_seconds: float = 1.0) -> IndexJob | None:
        message = self.sync_queue.dequeue(timeout_seconds=timeout_seconds)
        if message is None:
            return None
        return self.process_job(message.job_id, source_id=message.source_id)

    def process_job(self, job_id: str, *, source_id: str | None = None) -> IndexJob:
        job = self.job_service.get_job(job_id)
        if job is None:
            if source_id is not None:
                self.sync_queue.release_source_lock(source_id, job_id)
            raise KeyError(f"job {job_id} not found")

        try:
            if job.status is JobStatus.CANCELLED:
                return job
            source = self._get_runnable_source(job)
            flow = self.flows[source.type]
            return flow.run(source, job)
        except Exception as exc:
            return self.job_service.mark_failed(
                job,
                error_summary=str(exc),
                failed_count=job.failed_count,
                failure_stage=JobFailureStage.WORKER,
            )
        finally:
            self.sync_queue.release_source_lock(job.source_id, job.id)

    def recover_running_jobs(self) -> list[IndexJob]:
        recovered: list[IndexJob] = []
        for job in self.job_service.list_running_jobs():
            recovered.append(
                self.job_service.mark_failed(
                    job,
                    error_summary="worker interrupted before job finished",
                    failed_count=job.failed_count,
                    failure_stage=JobFailureStage.WORKER,
                )
            )
            self.sync_queue.release_source_lock(job.source_id, job.id)
        return recovered

    def _get_runnable_source(self, job: IndexJob) -> Source:
        source = self.source_service.get_source(job.source_id)
        if source is None:
            raise KeyError(f"source {job.source_id} not found")
        if not source.enabled:
            raise ValueError(f"source {job.source_id} is disabled")
        return source


class SyncWorker:
    def __init__(self, *, orchestrator: SyncOrchestrator, poll_timeout_seconds: float = 1.0) -> None:
        self.orchestrator = orchestrator
        self.poll_timeout_seconds = poll_timeout_seconds
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.orchestrator.recover_running_jobs()
        self._thread = Thread(target=self._run, name="sync-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.poll_timeout_seconds * 2, 1.0))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.orchestrator.process_next_job(timeout_seconds=self.poll_timeout_seconds)
            except Exception:
                logger.exception("sync worker loop failed")
                sleep(0.1)
