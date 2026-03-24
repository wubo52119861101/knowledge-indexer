from __future__ import annotations

from app.models.common import JobFailureStage, JobStatus, SourceType, SyncMode
from app.models.job import IndexJob
from app.models.source import Source
from app.repositories.checkpoint_repo import InMemoryCheckpointRepository
from app.repositories.job_repo import InMemoryJobRepository
from app.repositories.source_repo import InMemorySourceRepository
from app.services.job_service import JobService
from app.services.source_service import SourceService
from app.services.sync_orchestrator import SyncOrchestrator
from app.services.sync_queue import InMemorySyncQueue
from app.core.config import Settings


class SuccessFlow:
    def __init__(self, job_service: JobService) -> None:
        self.job_service = job_service

    def run(self, source: Source, job: IndexJob) -> IndexJob:
        self.job_service.mark_running(job)
        return self.job_service.mark_succeeded(job, processed_count=3, failed_count=0, checkpoint_after="30")


class FailingFlow:
    def run(self, source: Source, job: IndexJob) -> IndexJob:
        raise RuntimeError("worker boom")


def build_orchestrator(*, sync_run_inline: bool = False, flow=None) -> tuple[SyncOrchestrator, JobService, InMemorySyncQueue]:
    source_repo = InMemorySourceRepository()
    source_repo.add(
        Source(
            id="src_1",
            name="demo",
            type=SourceType.API,
            config={"base_url": "http://example.com"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )
    checkpoint_repo = InMemoryCheckpointRepository()
    checkpoint_repo.save("src_1", "default", "10")
    job_service = JobService(InMemoryJobRepository())
    queue = InMemorySyncQueue(lock_ttl_seconds=60)
    settings = Settings(app_env="test", sync_run_inline=sync_run_inline, sync_worker_enabled=False)
    orchestrator = SyncOrchestrator(
        settings=settings,
        source_service=SourceService(source_repo),
        checkpoint_repo=checkpoint_repo,
        job_service=job_service,
        sync_queue=queue,
        flows={SourceType.API: flow or SuccessFlow(job_service)},
    )
    return orchestrator, job_service, queue


def test_trigger_sync_enqueues_and_processes_job() -> None:
    orchestrator, job_service, queue = build_orchestrator(sync_run_inline=False)

    job = orchestrator.trigger_sync("src_1", SyncMode.INCREMENTAL, "tester")

    assert job.status is JobStatus.PENDING
    assert job.checkpoint_before == "10"
    assert queue.get_source_lock_owner("src_1") == job.id

    result = orchestrator.process_next_job(timeout_seconds=0.0)

    assert result is not None
    assert result.id == job.id
    assert result.status is JobStatus.SUCCEEDED
    assert result.processed_count == 3
    assert result.checkpoint_after == "30"
    assert job_service.get_job(job.id).status is JobStatus.SUCCEEDED
    assert queue.get_source_lock_owner("src_1") is None


def test_trigger_sync_rejects_duplicate_active_job() -> None:
    orchestrator, _job_service, _queue = build_orchestrator(sync_run_inline=False)

    first_job = orchestrator.trigger_sync("src_1", SyncMode.INCREMENTAL, "tester")

    assert first_job.status is JobStatus.PENDING
    try:
        orchestrator.trigger_sync("src_1", SyncMode.FULL, "tester")
    except ValueError as exc:
        assert first_job.id in str(exc)
    else:
        raise AssertionError("expected duplicate trigger to be rejected")


def test_process_next_job_marks_worker_failure() -> None:
    orchestrator, job_service, queue = build_orchestrator(sync_run_inline=False, flow=FailingFlow())

    job = orchestrator.trigger_sync("src_1", SyncMode.INCREMENTAL, "tester")
    result = orchestrator.process_next_job(timeout_seconds=0.0)

    assert result is not None
    assert result.id == job.id
    assert result.status is JobStatus.FAILED
    assert result.failure_stage is JobFailureStage.WORKER
    assert result.error_summary == "worker boom"
    assert job_service.get_job(job.id).status is JobStatus.FAILED
    assert queue.get_source_lock_owner("src_1") is None


def test_recover_running_jobs_marks_them_failed() -> None:
    orchestrator, job_service, queue = build_orchestrator(sync_run_inline=False)
    job = job_service.create_job(source_id="src_1", mode=SyncMode.INCREMENTAL, triggered_by="tester", job_id="job_running")
    job_service.mark_running(job)
    assert queue.acquire_source_lock("src_1", job.id)

    recovered = orchestrator.recover_running_jobs()

    assert len(recovered) == 1
    assert recovered[0].id == job.id
    assert recovered[0].status is JobStatus.FAILED
    assert recovered[0].failure_stage is JobFailureStage.WORKER
    assert "interrupted" in recovered[0].error_summary
    assert queue.get_source_lock_owner("src_1") is None
