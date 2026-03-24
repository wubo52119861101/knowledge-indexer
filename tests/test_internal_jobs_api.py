import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from app.core.container import get_container
from app.main import app
from app.models.common import SyncMode
from app.repositories.job_repo import InMemoryJobRepository
from app.services.job_service import JobService


class StubContainer:
    def __init__(self) -> None:
        self.job_service = JobService(InMemoryJobRepository())


def test_cancel_job_api_returns_cancelled_job_for_pending_job() -> None:
    container = StubContainer()
    job = container.job_service.create_job(source_id="src_1", mode=SyncMode.FULL, triggered_by="tester")
    app.dependency_overrides[get_container] = lambda: container
    client = TestClient(app)

    response = client.post(
        f"/internal/jobs/{job.id}/cancel",
        json={"operator": "system", "reason": "manual cancel"},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "CANCELLED"
    assert data["cancel_requested_by"] == "system"
    assert data["cancel_reason"] == "manual cancel"


def test_cancel_job_api_is_idempotent_for_running_job() -> None:
    container = StubContainer()
    job = container.job_service.create_job(source_id="src_1", mode=SyncMode.FULL, triggered_by="tester")
    container.job_service.mark_running(job)
    app.dependency_overrides[get_container] = lambda: container
    client = TestClient(app)

    first_response = client.post(
        f"/internal/jobs/{job.id}/cancel",
        json={"operator": "system", "reason": "manual cancel"},
    )
    second_response = client.post(
        f"/internal/jobs/{job.id}/cancel",
        json={"operator": "other", "reason": "ignored"},
    )

    app.dependency_overrides.clear()
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_data = first_response.json()["data"]
    second_data = second_response.json()["data"]
    assert first_data["status"] == "CANCELLING"
    assert second_data["status"] == "CANCELLING"
    assert second_data["cancel_requested_by"] == "system"
    assert second_data["cancel_reason"] == "manual cancel"
    assert second_data["cancel_requested_at"] == first_data["cancel_requested_at"]


def test_cancel_job_api_returns_conflict_for_completed_job() -> None:
    container = StubContainer()
    job = container.job_service.create_job(source_id="src_1", mode=SyncMode.FULL, triggered_by="tester")
    container.job_service.mark_succeeded(job, processed_count=1, failed_count=0)
    app.dependency_overrides[get_container] = lambda: container
    client = TestClient(app)

    response = client.post(
        f"/internal/jobs/{job.id}/cancel",
        json={"operator": "system", "reason": "manual cancel"},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 409
    assert response.json()["detail"] == f"job {job.id} is already completed"
