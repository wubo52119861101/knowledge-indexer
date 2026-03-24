from __future__ import annotations

from app.core.config import Settings
from app.models.common import EvidenceStatus
from app.schemas.retrieval import AclContext, AskResponseData, SearchFilters, SearchItem, SearchResponseData
from app.services.answer_generator import AnswerGenerator, NoopAnswerGenerator
from app.services.pipeline_engine_service import PipelineEngineService
from app.services.rerank_service import NoopRerankService, RerankService
from app.services.retrieval_service import RetrievalService


class QaService:
    def __init__(
        self,
        settings: Settings,
        retrieval_service: RetrievalService,
        answer_generator: AnswerGenerator | None = None,
        rerank_service: RerankService | None = None,
        pipeline_engine_service: PipelineEngineService | None = None,
    ) -> None:
        self.settings = settings
        self.retrieval_service = retrieval_service
        self.answer_generator = answer_generator or NoopAnswerGenerator(settings)
        self.rerank_service = rerank_service or NoopRerankService(settings)
        self.pipeline_engine_service = pipeline_engine_service or PipelineEngineService(settings)

    def search(self, query: str, top_k: int, filters: SearchFilters, acl_context: AclContext) -> SearchResponseData:
        items = self.retrieval_service.search(
            query=query,
            top_k=top_k,
            filters=filters,
            acl_context=acl_context,
        )
        reranked_items, rerank_applied = self.rerank_service.rerank(query, items)
        return SearchResponseData(
            items=reranked_items,
            pipeline_engine=self.pipeline_engine_service.resolve("search"),
            rerank_applied=rerank_applied,
        )

    def ask(self, question: str, top_k: int, filters: SearchFilters, acl_context: AclContext) -> AskResponseData:
        items = self.retrieval_service.search(
            query=question,
            top_k=top_k,
            filters=filters,
            acl_context=acl_context,
        )
        pipeline_engine = self.pipeline_engine_service.resolve("ask")
        evidence_status, reason = self._evaluate_evidence(items)
        if evidence_status is EvidenceStatus.INSUFFICIENT:
            return AskResponseData(
                answer="当前证据不足，暂时无法给出可靠答案。",
                citations=items,
                evidence_status=evidence_status,
                reason=reason,
                answer_mode="fallback",
                pipeline_engine=pipeline_engine,
                rerank_applied=False,
            )

        reranked_items, rerank_applied = self.rerank_service.rerank(question, items)
        evidence_items = reranked_items[: min(self.settings.ask_evidence_top_n, len(reranked_items))]

        generated_answer = self.answer_generator.generate(question, evidence_items)
        if generated_answer:
            return AskResponseData(
                answer=generated_answer,
                citations=evidence_items,
                evidence_status=EvidenceStatus.SUFFICIENT,
                reason=None,
                answer_mode="generated",
                pipeline_engine=pipeline_engine,
                rerank_applied=rerank_applied,
            )

        fallback_reason = "LLM 调用失败" if self.answer_generator.enabled else "LLM 未启用"
        return AskResponseData(
            answer=self._build_supported_fallback(evidence_items),
            citations=evidence_items,
            evidence_status=EvidenceStatus.SUFFICIENT,
            reason=fallback_reason,
            answer_mode="fallback",
            pipeline_engine=pipeline_engine,
            rerank_applied=rerank_applied,
        )

    def _evaluate_evidence(self, items: list[SearchItem]) -> tuple[EvidenceStatus, str | None]:
        if len(items) < self.settings.min_evidence_count:
            return EvidenceStatus.INSUFFICIENT, "检索命中数量不足"
        if not items or items[0].score < self.settings.search_score_threshold:
            return EvidenceStatus.INSUFFICIENT, "检索分数低于阈值"
        return EvidenceStatus.SUFFICIENT, None

    def _build_supported_fallback(self, evidence_items: list[SearchItem]) -> str:
        if not evidence_items:
            return "当前证据不足，暂时无法给出可靠答案。"

        lines = ["已检索到相关依据，但当前未生成结构化答案，请结合以下引用内容核实："]
        for index, item in enumerate(evidence_items, start=1):
            snippet = " ".join(item.content.split())
            snippet = snippet[:160].rstrip()
            if len(item.content) > 160:
                snippet = f"{snippet}..."
            lines.append(f"{index}. {item.document.title}: {snippet}")
        return "\n".join(lines)
