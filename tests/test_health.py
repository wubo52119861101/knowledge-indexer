import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from app.api import health as health_api
from app.core.config import Settings
from app.main import app



def test_health_reports_layered_dependency_states(monkeypatch) -> None:
    monkeypatch.setattr(
        health_api,
        "get_settings",
        lambda: Settings(app_name="knowledge-indexer", app_env="test", embedding_provider="hash"),
    )
    monkeypatch.setattr(
        health_api,
        "check_database_health",
        lambda settings: {
            "status": "reachable",
            "detail": "db ok",
            "layers": {
                "configuration": "configured",
                "connectivity": "reachable",
                "capability": "repository_ready",
            },
        },
    )
    monkeypatch.setattr(
        health_api,
        "check_redis_health",
        lambda settings: {
            "status": "reachable",
            "detail": "redis ok",
            "layers": {
                "configuration": "configured",
                "connectivity": "reachable",
                "capability": "queue_ready",
            },
        },
    )
    monkeypatch.setattr(
        health_api,
        "check_minio_health",
        lambda settings: {
            "status": "reachable",
            "detail": "minio ok",
            "layers": {
                "configuration": "configured",
                "connectivity": "reachable",
                "capability": "archive_ready",
            },
        },
    )
    monkeypatch.setattr(
        health_api,
        "check_embedding_health",
        lambda settings: {
            "status": "development",
            "detail": "hash ok",
            "layers": {
                "configuration": "builtin",
                "connectivity": "not_required",
                "capability": "embedding_development",
            },
            "provider": "hash",
        },
    )

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["app"]["env"] == "test"
    assert payload["database"]["layers"]["connectivity"] == "reachable"
    assert payload["redis"]["layers"]["capability"] == "queue_ready"
    assert payload["minio"]["status"] == "reachable"
    assert payload["embedding"]["provider"] == "hash"
    assert payload["pipeline_engine"]["engine"] == "builtin"
