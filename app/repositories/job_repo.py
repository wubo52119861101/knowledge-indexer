from __future__ import annotations

from app.models.job import IndexJob


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, IndexJob] = {}

    def add(self, job: IndexJob) -> IndexJob:
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> IndexJob | None:
        return self._jobs.get(job_id)

    def latest_for_source(self, source_id: str) -> IndexJob | None:
        source_jobs = [job for job in self._jobs.values() if job.source_id == source_id]
        source_jobs.sort(key=lambda item: item.created_at, reverse=True)
        return source_jobs[0] if source_jobs else None

    def save(self, job: IndexJob) -> IndexJob:
        self._jobs[job.id] = job
        return job
