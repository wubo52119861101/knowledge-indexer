from __future__ import annotations

from app.models.common import JobFailureStage, JobStatus, SyncMode, generate_id, utcnow
from app.models.job import IndexJob
from app.repositories.job_repo import JobRepository


class JobService:
    def __init__(self, job_repo: JobRepository) -> None:
        self.job_repo = job_repo

    def create_job(
        self,
        source_id: str,
        mode: SyncMode,
        triggered_by: str,
        *,
        job_id: str | None = None,
        checkpoint_before: str | None = None,
    ) -> IndexJob:
        job = IndexJob(
            id=job_id or generate_id("job"),
            source_id=source_id,
            mode=mode,
            status=JobStatus.PENDING,
            triggered_by=triggered_by,
            checkpoint_before=checkpoint_before,
        )
        return self.job_repo.add(job)

    def get_job(self, job_id: str) -> IndexJob | None:
        return self.job_repo.get(job_id)

    def latest_for_source(self, source_id: str) -> IndexJob | None:
        return self.job_repo.latest_for_source(source_id)

    def get_active_job_for_source(self, source_id: str) -> IndexJob | None:
        return self.job_repo.active_for_source(source_id)

    def list_running_jobs(self) -> list[IndexJob]:
        return self.job_repo.list_running()

    def save(self, job: IndexJob) -> IndexJob:
        return self.job_repo.save(job)

    def set_snapshot_path(self, job: IndexJob, snapshot_path: str | None) -> IndexJob:
        job.snapshot_path = snapshot_path
        return self.job_repo.save(job)

    def mark_running(self, job: IndexJob) -> IndexJob:
        job.status = JobStatus.RUNNING
        job.error_summary = None
        job.failure_stage = None
        job.started_at = utcnow()
        job.finished_at = None
        return self.job_repo.save(job)

    def update_progress(
        self,
        job: IndexJob,
        *,
        processed_count: int | None = None,
        failed_count: int | None = None,
        checkpoint_after: str | None = None,
    ) -> IndexJob:
        if processed_count is not None:
            job.processed_count = processed_count
        if failed_count is not None:
            job.failed_count = failed_count
        if checkpoint_after is not None:
            job.checkpoint_after = checkpoint_after
        return self.job_repo.save(job)

    def mark_succeeded(
        self,
        job: IndexJob,
        processed_count: int,
        failed_count: int,
        *,
        checkpoint_after: str | None = None,
    ) -> IndexJob:
        job.status = JobStatus.SUCCEEDED
        job.processed_count = processed_count
        job.failed_count = failed_count
        job.error_summary = None
        job.failure_stage = None
        job.checkpoint_after = checkpoint_after
        job.finished_at = utcnow()
        return self.job_repo.save(job)

    def mark_failed(
        self,
        job: IndexJob,
        error_summary: str,
        *,
        failed_count: int | None = None,
        failure_stage: JobFailureStage | None = None,
        checkpoint_after: str | None = None,
    ) -> IndexJob:
        job.status = JobStatus.FAILED
        job.error_summary = error_summary
        if failed_count is not None:
            job.failed_count = failed_count
        job.failure_stage = failure_stage
        job.checkpoint_after = checkpoint_after
        if job.started_at is None:
            job.started_at = utcnow()
        job.finished_at = utcnow()
        return self.job_repo.save(job)

    def mark_cancelled(self, job: IndexJob, reason: str | None = None) -> IndexJob:
        job.status = JobStatus.CANCELLED
        job.error_summary = reason
        if job.started_at is None:
            job.started_at = utcnow()
        job.finished_at = utcnow()
        return self.job_repo.save(job)
