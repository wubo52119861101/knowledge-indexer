from app.core.config import Settings
from app.schemas.retrieval import AclContext, CitationItem, SearchDocument, SearchFilters, SearchItem, SearchSource
from app.services.qa_service import QaService


class StubRetrievalService:
    def __init__(self, items: list[SearchItem]) -> None:
        self.items = items

    def search(self, query: str, top_k: int, filters: SearchFilters, acl_context: AclContext) -> list[SearchItem]:
        return self.items[:top_k]


class StubAnswerGenerator:
    def __init__(self, answer: str | None, enabled: bool = True) -> None:
        self.answer = answer
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def generate(self, question: str, evidence_items: list[SearchItem]) -> str | None:
        return self.answer


class StubRerankService:
    def __init__(self, reordered_items: list[SearchItem] | None = None, applied: bool = False) -> None:
        self.reordered_items = reordered_items
        self.applied = applied

    @property
    def enabled(self) -> bool:
        return self.applied

    def rerank(self, query: str, items: list[SearchItem]) -> tuple[list[SearchItem], bool]:
        return self.reordered_items or items, self.applied


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


def test_qa_service_returns_insufficient_when_score_is_low() -> None:
    qa_service = QaService(
        settings=Settings(SEARCH_SCORE_THRESHOLD=0.9, MIN_EVIDENCE_COUNT=1),
        retrieval_service=StubRetrievalService(
            [make_search_item("chk_1", 0.32, "库存盘点流程说明。", "无关文档")]
        ),
    )

    answer = qa_service.ask(
        question="退款多久到账",
        top_k=5,
        filters=SearchFilters(),
        acl_context=AclContext(),
    )

    assert answer.evidence_status == "INSUFFICIENT"
    assert answer.reason == "检索分数低于阈值"
    assert answer.answer_mode == "fallback"


def test_qa_service_returns_generated_answer_with_reranked_citations() -> None:
    item_a = make_search_item("chk_a", 0.91, "退款到账通常需要 3 个工作日。", "退款规则")
    item_b = make_search_item("chk_b", 0.88, "如遇节假日，到账时间可能顺延。", "到账时效")
    qa_service = QaService(
        settings=Settings(SEARCH_SCORE_THRESHOLD=0.2, MIN_EVIDENCE_COUNT=1, ASK_EVIDENCE_TOP_N=2),
        retrieval_service=StubRetrievalService([item_a, item_b]),
        answer_generator=StubAnswerGenerator("退款通常会在 3 个工作日内到账，节假日可能顺延。"),
        rerank_service=StubRerankService([item_b, item_a], applied=True),
    )

    answer = qa_service.ask(
        question="退款多久到账",
        top_k=5,
        filters=SearchFilters(),
        acl_context=AclContext(),
    )

    assert answer.answer_mode == "generated"
    assert answer.evidence_status == "SUFFICIENT"
    assert answer.rerank_applied is True
    assert [item.chunk_id for item in answer.citations] == ["chk_b", "chk_a"]


def test_qa_service_falls_back_when_llm_is_disabled() -> None:
    item = make_search_item("chk_1", 0.93, "退款到账通常需要 1 到 3 个工作日。", "退款时效")
    qa_service = QaService(
        settings=Settings(SEARCH_SCORE_THRESHOLD=0.2, MIN_EVIDENCE_COUNT=1),
        retrieval_service=StubRetrievalService([item]),
        answer_generator=StubAnswerGenerator(answer=None, enabled=False),
        rerank_service=StubRerankService(applied=False),
    )

    answer = qa_service.ask(
        question="退款多久到账",
        top_k=5,
        filters=SearchFilters(),
        acl_context=AclContext(),
    )

    assert answer.answer_mode == "fallback"
    assert answer.evidence_status == "SUFFICIENT"
    assert answer.reason == "LLM 未启用"
    assert "已检索到相关依据" in answer.answer
    assert [item.chunk_id for item in answer.citations] == ["chk_1"]


def test_qa_service_search_returns_rerank_metadata() -> None:
    item_a = make_search_item("chk_a", 0.85, "第一条证据", "文档 A")
    item_b = make_search_item("chk_b", 0.83, "第二条证据", "文档 B")
    qa_service = QaService(
        settings=Settings(),
        retrieval_service=StubRetrievalService([item_a, item_b]),
        rerank_service=StubRerankService([item_b, item_a], applied=True),
    )

    response = qa_service.search(
        query="测试查询",
        top_k=5,
        filters=SearchFilters(),
        acl_context=AclContext(),
    )

    assert response.rerank_applied is True
    assert response.pipeline_engine.scene == "search"
    assert [item.chunk_id for item in response.items] == ["chk_b", "chk_a"]
