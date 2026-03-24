import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import ServiceContainer, get_container
from app.main import app


def test_health_returns_pipeline_engine_from_service_configuration() -> None:
    container = ServiceContainer(Settings(PIPELINE_ENGINE_TYPE="external", PIPELINE_ENGINE_NAME="cocoindex"))
    app.dependency_overrides[get_container] = lambda: container
    client = TestClient(app)

    response = client.get("/health")

    app.dependency_overrides.clear()
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pipeline_engine"] == {
        "type": "external",
        "name": "cocoindex",
        "scene": "service",
    }
