import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from app.core.container import get_container
from app.main import app
from app.models.common import EvidenceStatus, PipelineEngineInfo, PipelineEngineType
from app.schemas.retrieval import AskResponseData, SearchResponseData


class StubQaService:
    def ask(self, question, top_k, filters, acl_context):
        return AskResponseData(
            answer="生成态答案",
            citations=[],
            evidence_status=EvidenceStatus.SUFFICIENT,
            reason=None,
            answer_mode="generated",
            pipeline_engine=PipelineEngineInfo(
                type=PipelineEngineType.BUILTIN,
                name="knowledge-indexer",
                scene="ask",
            ),
            rerank_applied=True,
        )

    def search(self, query, top_k, filters, acl_context):
        return SearchResponseData(
            items=[],
            pipeline_engine=PipelineEngineInfo(
                type=PipelineEngineType.BUILTIN,
                name="knowledge-indexer",
                scene="search",
            ),
            rerank_applied=True,
        )


class StubContainer:
    def __init__(self) -> None:
        self.qa_service = StubQaService()


def test_internal_ask_returns_extended_fields() -> None:
    app.dependency_overrides[get_container] = lambda: StubContainer()
    client = TestClient(app)

    response = client.post(
        "/internal/ask",
        json={"question": "退款多久到账", "top_k": 5, "filters": {}, "acl_context": {}},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["answer_mode"] == "generated"
    assert data["rerank_applied"] is True
    assert data["pipeline_engine"]["scene"] == "ask"


def test_internal_search_returns_extended_fields() -> None:
    app.dependency_overrides[get_container] = lambda: StubContainer()
    client = TestClient(app)

    response = client.post(
        "/internal/search",
        json={"query": "退款", "top_k": 5, "filters": {}, "acl_context": {}},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["rerank_applied"] is True
    assert data["pipeline_engine"]["scene"] == "search"
