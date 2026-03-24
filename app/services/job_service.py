from __future__ import annotations

from app.models.common import JobStatus, PipelineEngineInfo, SyncMode, generate_id, utcnow
from app.models.job import IndexJob
from app.repositories.job_repo import InMemoryJobRepository


class JobCancellationConflictError(Exception):
    pass


class JobService:
    def __init__(self, job_repo: InMemoryJobRepository) -> None:
        self.job_repo = job_repo

    def create_job(
        self,
        source_id: str,
        mode: SyncMode,
        triggered_by: str,
        pipeline_engine: PipelineEngineInfo | None = None,
    ) -> IndexJob:
        job = IndexJob(
            id=generate_id("job"),
            source_id=source_id,
            mode=mode,
            status=JobStatus.PENDING,
            triggered_by=triggered_by,
            pipeline_engine=pipeline_engine,
        )
        return self.job_repo.add(job)

    def get_job(self, job_id: str) -> IndexJob | None:
        return self.job_repo.get(job_id)

    def latest_for_source(self, source_id: str) -> IndexJob | None:
        return self.job_repo.latest_for_source(source_id)

    def mark_running(self, job: IndexJob) -> IndexJob:
        current_job = self.refresh(job)
        if current_job.status is not JobStatus.PENDING:
            return self.job_repo.save(current_job)
        current_job.status = JobStatus.RUNNING
        current_job.started_at = current_job.started_at or utcnow()
        return self.job_repo.save(current_job)

    def mark_succeeded(self, job: IndexJob, processed_count: int, failed_count: int) -> IndexJob:
        current_job = self.refresh(job)
        if current_job.status in {JobStatus.CANCELLING, JobStatus.CANCELLED}:
            return self.mark_cancelled(current_job)
        current_job.status = JobStatus.SUCCEEDED
        current_job.processed_count = processed_count
        current_job.failed_count = failed_count
        current_job.finished_at = utcnow()
        return self.job_repo.save(current_job)

    def mark_failed(self, job: IndexJob, error_summary: str, failed_count: int = 0) -> IndexJob:
        current_job = self.refresh(job)
        if current_job.status in {JobStatus.CANCELLING, JobStatus.CANCELLED}:
            return self.mark_cancelled(current_job)
        current_job.status = JobStatus.FAILED
        current_job.error_summary = error_summary
        current_job.failed_count = failed_count
        current_job.finished_at = utcnow()
        return self.job_repo.save(current_job)

    def request_cancel(self, job_id: str, operator: str, reason: str | None = None) -> IndexJob:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)

        if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
            raise JobCancellationConflictError(f"job {job_id} is already completed")

        if job.status in {JobStatus.CANCELLING, JobStatus.CANCELLED}:
            return job

        job.cancel_requested_at = utcnow()
        job.cancel_requested_by = operator
        job.cancel_reason = reason

        if job.status is JobStatus.PENDING:
            return self.mark_cancelled(job)

        job.status = JobStatus.CANCELLING
        return self.job_repo.save(job)

    def mark_cancelled(self, job: IndexJob) -> IndexJob:
        current_job = self.refresh(job)
        current_job.status = JobStatus.CANCELLED
        current_job.error_summary = None
        current_job.finished_at = current_job.finished_at or utcnow()
        return self.job_repo.save(current_job)

    def is_cancel_requested(self, job: IndexJob) -> bool:
        return self.refresh(job).status in {JobStatus.CANCELLING, JobStatus.CANCELLED}

    def refresh(self, job: IndexJob) -> IndexJob:
        return self.job_repo.get(job.id) or job
