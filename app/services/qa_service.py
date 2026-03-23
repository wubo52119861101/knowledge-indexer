from __future__ import annotations

from app.core.config import Settings
from app.models.common import EvidenceStatus
from app.schemas.retrieval import AskResponseData, SearchFilters, AclContext
from app.services.retrieval_service import RetrievalService


class QaService:
    def __init__(self, settings: Settings, retrieval_service: RetrievalService) -> None:
        self.settings = settings
        self.retrieval_service = retrieval_service

    def ask(self, question: str, top_k: int, filters: SearchFilters, acl_context: AclContext) -> AskResponseData:
        items = self.retrieval_service.search(
            query=question,
            top_k=top_k,
            filters=filters,
            acl_context=acl_context,
        )
        if len(items) < self.settings.min_evidence_count:
            return AskResponseData(
                answer="当前证据不足，暂时无法给出可靠答案。",
                citations=items,
                evidence_status=EvidenceStatus.INSUFFICIENT,
                reason="检索命中数量不足",
            )
        if not items or items[0].score < self.settings.search_score_threshold:
            return AskResponseData(
                answer="当前证据不足，暂时无法给出可靠答案。",
                citations=items,
                evidence_status=EvidenceStatus.INSUFFICIENT,
                reason="检索分数低于阈值",
            )

        cited_texts = [f"- {item.content}" for item in items[: min(3, len(items))]]
        answer = "根据知识库检索结果，可确认以下信息：\n" + "\n".join(cited_texts)
        return AskResponseData(
            answer=answer,
            citations=items,
            evidence_status=EvidenceStatus.SUFFICIENT,
            reason=None,
        )
