from unittest.mock import patch

import httpx

from app.core.config import Settings
from app.schemas.retrieval import CitationItem, SearchDocument, SearchItem, SearchSource
from app.services.rerank_service import RerankService


class StubResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://rerank.example")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("rerank failed", request=request, response=response)

    def json(self) -> object:
        return self.payload


def make_search_item(chunk_id: str, score: float, content: str, title: str) -> SearchItem:
    return SearchItem(
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        score=score,
        content=content,
        source=SearchSource(source_id="src_1", source_type="file"),
        document=SearchDocument(title=title, external_id=f"ext_{chunk_id}"),
        citation=CitationItem(doc_title=title, chunk_index=0),
    )


def test_rerank_service_reorders_items_when_provider_returns_ranked_ids() -> None:
    item_a = make_search_item("chk_a", 0.80, "A", "文档 A")
    item_b = make_search_item("chk_b", 0.79, "B", "文档 B")
    service = RerankService(Settings(RERANK_ENABLED=True, RERANK_BASE_URL="http://rerank.example"))

    with patch.object(httpx.Client, "post", return_value=StubResponse({"results": [{"id": "chk_b"}, {"id": "chk_a"}]})):
        reranked_items, applied = service.rerank("测试查询", [item_a, item_b])

    assert applied is True
    assert [item.chunk_id for item in reranked_items] == ["chk_b", "chk_a"]


def test_rerank_service_falls_back_to_original_order_when_provider_fails() -> None:
    item_a = make_search_item("chk_a", 0.80, "A", "文档 A")
    item_b = make_search_item("chk_b", 0.79, "B", "文档 B")
    service = RerankService(Settings(RERANK_ENABLED=True, RERANK_BASE_URL="http://rerank.example"))

    with patch.object(httpx.Client, "post", side_effect=httpx.ConnectError("boom")):
        reranked_items, applied = service.rerank("测试查询", [item_a, item_b])

    assert applied is False
    assert [item.chunk_id for item in reranked_items] == ["chk_a", "chk_b"]


def test_rerank_service_falls_back_to_original_order_when_response_is_invalid() -> None:
    item_a = make_search_item("chk_a", 0.80, "A", "文档 A")
    item_b = make_search_item("chk_b", 0.79, "B", "文档 B")
    service = RerankService(Settings(RERANK_ENABLED=True, RERANK_BASE_URL="http://rerank.example"))

    with patch.object(httpx.Client, "post", return_value=StubResponse({"unexpected": []})):
        reranked_items, applied = service.rerank("测试查询", [item_a, item_b])

    assert applied is False
    assert [item.chunk_id for item in reranked_items] == ["chk_a", "chk_b"]
