import pytest

from app.models.common import JobStatus, SyncMode
from app.repositories.job_repo import InMemoryJobRepository
from app.services.job_service import JobCancellationConflictError, JobService


def build_job_service() -> JobService:
    return JobService(InMemoryJobRepository())


def test_request_cancel_marks_pending_job_cancelled() -> None:
    service = build_job_service()
    job = service.create_job(source_id="src_1", mode=SyncMode.FULL, triggered_by="tester")

    cancelled = service.request_cancel(job.id, operator="system", reason="manual cancel")

    assert cancelled.status is JobStatus.CANCELLED
    assert cancelled.cancel_requested_by == "system"
    assert cancelled.cancel_reason == "manual cancel"
    assert cancelled.cancel_requested_at is not None
    assert cancelled.finished_at is not None


def test_request_cancel_marks_running_job_cancelling_idempotently() -> None:
    service = build_job_service()
    job = service.create_job(source_id="src_1", mode=SyncMode.FULL, triggered_by="tester")
    running = service.mark_running(job)

    cancelling = service.request_cancel(running.id, operator="system", reason="manual cancel")
    cancelled_again = service.request_cancel(running.id, operator="other", reason="ignored")

    assert cancelling.status is JobStatus.CANCELLING
    assert cancelled_again.status is JobStatus.CANCELLING
    assert cancelled_again.cancel_requested_by == "system"
    assert cancelled_again.cancel_reason == "manual cancel"
    assert cancelled_again.cancel_requested_at == cancelling.cancel_requested_at


def test_request_cancel_completed_job_raises_conflict() -> None:
    service = build_job_service()
    job = service.create_job(source_id="src_1", mode=SyncMode.FULL, triggered_by="tester")
    service.mark_succeeded(job, processed_count=1, failed_count=0)

    with pytest.raises(JobCancellationConflictError):
        service.request_cancel(job.id, operator="system", reason="manual cancel")
