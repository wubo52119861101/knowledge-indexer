from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.core.database import PostgresRepositoryBase
from app.models.common import JobStatus
from app.models.job import IndexJob


class JobRepository(Protocol):
    def add(self, job: IndexJob) -> IndexJob: ...

    def get(self, job_id: str) -> IndexJob | None: ...

    def latest_for_source(self, source_id: str) -> IndexJob | None: ...

    def active_for_source(self, source_id: str) -> IndexJob | None: ...

    def list_running(self) -> list[IndexJob]: ...

    def save(self, job: IndexJob) -> IndexJob: ...


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

    def active_for_source(self, source_id: str) -> IndexJob | None:
        source_jobs = [job for job in self._jobs.values() if job.source_id == source_id and job.is_active]
        source_jobs.sort(key=lambda item: item.created_at, reverse=True)
        return source_jobs[0] if source_jobs else None

    def list_running(self) -> list[IndexJob]:
        jobs = [job for job in self._jobs.values() if job.status is JobStatus.RUNNING]
        jobs.sort(key=lambda item: item.created_at)
        return jobs

    def save(self, job: IndexJob) -> IndexJob:
        self._jobs[job.id] = job
        return job


class PostgresJobRepository(PostgresRepositoryBase):
    def add(self, job: IndexJob) -> IndexJob:
        self._execute(
            """
            INSERT INTO kb_sync_jobs (
                id, source_id, mode, status, triggered_by,
                processed_count, failed_count, error_summary, failure_stage, snapshot_path,
                checkpoint_before, checkpoint_after, started_at, finished_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                job.id,
                job.source_id,
                job.mode.value,
                job.status.value,
                job.triggered_by,
                job.processed_count,
                job.failed_count,
                job.error_summary,
                job.failure_stage.value if job.failure_stage else None,
                job.snapshot_path,
                job.checkpoint_before,
                job.checkpoint_after,
                job.started_at,
                job.finished_at,
                job.created_at,
            ),
        )
        return job

    def get(self, job_id: str) -> IndexJob | None:
        row = self._fetchone(
            """
            SELECT id, source_id, mode, status, triggered_by, processed_count,
                   failed_count, error_summary, failure_stage, snapshot_path,
                   checkpoint_before, checkpoint_after, started_at, finished_at, created_at
            FROM kb_sync_jobs
            WHERE id = %s
            """,
            (job_id,),
        )
        if row is None:
            return None
        return self._to_model(row)

    def latest_for_source(self, source_id: str) -> IndexJob | None:
        row = self._fetchone(
            """
            SELECT id, source_id, mode, status, triggered_by, processed_count,
                   failed_count, error_summary, failure_stage, snapshot_path,
                   checkpoint_before, checkpoint_after, started_at, finished_at, created_at
            FROM kb_sync_jobs
            WHERE source_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_id,),
        )
        if row is None:
            return None
        return self._to_model(row)

    def active_for_source(self, source_id: str) -> IndexJob | None:
        row = self._fetchone(
            """
            SELECT id, source_id, mode, status, triggered_by, processed_count,
                   failed_count, error_summary, failure_stage, snapshot_path,
                   checkpoint_before, checkpoint_after, started_at, finished_at, created_at
            FROM kb_sync_jobs
            WHERE source_id = %s AND status IN (%s, %s)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_id, JobStatus.PENDING.value, JobStatus.RUNNING.value),
        )
        if row is None:
            return None
        return self._to_model(row)

    def list_running(self) -> list[IndexJob]:
        rows = self._fetchall(
            """
            SELECT id, source_id, mode, status, triggered_by, processed_count,
                   failed_count, error_summary, failure_stage, snapshot_path,
                   checkpoint_before, checkpoint_after, started_at, finished_at, created_at
            FROM kb_sync_jobs
            WHERE status = %s
            ORDER BY created_at ASC
            """,
            (JobStatus.RUNNING.value,),
        )
        return [self._to_model(row) for row in rows]

    def save(self, job: IndexJob) -> IndexJob:
        self._execute(
            """
            UPDATE kb_sync_jobs
            SET status = %s,
                processed_count = %s,
                failed_count = %s,
                error_summary = %s,
                failure_stage = %s,
                snapshot_path = %s,
                checkpoint_before = %s,
                checkpoint_after = %s,
                started_at = %s,
                finished_at = %s
            WHERE id = %s
            """,
            (
                job.status.value,
                job.processed_count,
                job.failed_count,
                job.error_summary,
                job.failure_stage.value if job.failure_stage else None,
                job.snapshot_path,
                job.checkpoint_before,
                job.checkpoint_after,
                job.started_at,
                job.finished_at,
                job.id,
            ),
        )
        return job

    def _to_model(self, row: dict) -> IndexJob:
        from app.models.common import JobFailureStage, JobStatus, SyncMode

        return IndexJob(
            id=row["id"],
            source_id=row["source_id"],
            mode=SyncMode(row["mode"]),
            status=JobStatus(row["status"]),
            triggered_by=row["triggered_by"],
            processed_count=int(row["processed_count"]),
            failed_count=int(row["failed_count"]),
            error_summary=row["error_summary"],
            failure_stage=JobFailureStage(row["failure_stage"]) if row["failure_stage"] else None,
            snapshot_path=row["snapshot_path"],
            checkpoint_before=row["checkpoint_before"],
            checkpoint_after=row["checkpoint_after"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            created_at=row["created_at"],
        )
