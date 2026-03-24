from __future__ import annotations

from app.models.common import JobStatus, PipelineEngineInfo, SyncMode, generate_id, utcnow
from app.models.job import IndexJob
from app.repositories.job_repo import InMemoryJobRepository


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
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        return self.job_repo.save(job)

    def mark_succeeded(self, job: IndexJob, processed_count: int, failed_count: int) -> IndexJob:
        job.status = JobStatus.SUCCEEDED
        job.processed_count = processed_count
        job.failed_count = failed_count
        job.finished_at = utcnow()
        return self.job_repo.save(job)

    def mark_failed(self, job: IndexJob, error_summary: str, failed_count: int = 0) -> IndexJob:
        job.status = JobStatus.FAILED
        job.error_summary = error_summary
        job.failed_count = failed_count
        job.finished_at = utcnow()
        return self.job_repo.save(job)
