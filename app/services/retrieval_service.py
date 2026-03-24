from __future__ import annotations

from typing import Protocol

from app.models.common import DocumentStatus
from app.models.document import Document, DocumentAcl
from app.repositories.chunk_repo import ChunkRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.source_repo import SourceRepository
from app.schemas.retrieval import AclContext, CitationItem, SearchDocument, SearchFilters, SearchItem, SearchSource
from app.services.embedding_service import EmbeddingService


class RerankService(Protocol):
    def rerank(self, query: str, items: list[SearchItem]) -> list[SearchItem]: ...


class RetrievalService:
    def __init__(
        self,
        source_repo: SourceRepository,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        embedding_service: EmbeddingService,
        min_score_threshold: float = 0.0,
        candidate_multiplier: int = 4,
        rerank_service: RerankService | None = None,
    ) -> None:
        self.source_repo = source_repo
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.embedding_service = embedding_service
        self.min_score_threshold = min_score_threshold
        self.candidate_multiplier = max(1, candidate_multiplier)
        self.rerank_service = rerank_service

    def search(
        self,
        query: str,
        top_k: int,
        filters: SearchFilters,
        acl_context: AclContext,
    ) -> list[SearchItem]:
        query_embedding = self.embedding_service.embed(query)
        candidate_limit = max(top_k, top_k * self.candidate_multiplier)
        candidates = self.chunk_repo.search_candidates(query_embedding, filters, candidate_limit)
        items: list[SearchItem] = []

        for candidate in candidates:
            chunk = candidate.chunk
            document = self.document_repo.get(chunk.document_id)
            if document is None or document.status is not DocumentStatus.ACTIVE:
                continue
            source = self.source_repo.get(document.source_id)
            if source is None:
                continue
            if not self._match_filters(document, filters):
                continue
            if not self._has_access(document, acl_context):
                continue
            if candidate.score < self.min_score_threshold:
                continue

            items.append(
                SearchItem(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    score=round(candidate.score, 4),
                    content=chunk.content,
                    source=SearchSource(source_id=source.id, source_type=source.type.value),
                    document=SearchDocument(title=document.title, external_id=document.external_doc_id),
                    citation=CitationItem(doc_title=document.title, chunk_index=chunk.chunk_index),
                )
            )

        if self.rerank_service is not None and items:
            items = self.rerank_service.rerank(query, items)

        items.sort(key=lambda item: item.score, reverse=True)
        return items[:top_k]

    def _match_filters(self, document: Document, filters: SearchFilters) -> bool:
        if filters.source_ids and document.source_id not in filters.source_ids:
            return False
        if filters.doc_types and document.doc_type not in filters.doc_types:
            return False
        for key, value in filters.metadata.items():
            if document.metadata.get(key) != value:
                return False
        return True

    def _has_access(self, document: Document, acl_context: AclContext) -> bool:
        acl_entries = document.acl_entries
        if not acl_entries:
            return True
        if self._matches_effect(acl_entries, acl_context, effect="deny"):
            return False
        allow_entries = [entry for entry in acl_entries if entry.effect.value == "allow"]
        if not allow_entries:
            return True
        return self._matches_entries(allow_entries, acl_context)

    def _matches_effect(self, acl_entries: list[DocumentAcl], acl_context: AclContext, effect: str) -> bool:
        entries = [entry for entry in acl_entries if entry.effect.value == effect]
        return self._matches_entries(entries, acl_context)

    def _matches_entries(self, acl_entries: list[DocumentAcl], acl_context: AclContext) -> bool:
        for entry in acl_entries:
            if entry.acl_type.value == "user" and acl_context.user_id == entry.acl_value:
                return True
            if entry.acl_type.value == "role" and entry.acl_value in acl_context.roles:
                return True
            if entry.acl_type.value == "department" and entry.acl_value in acl_context.departments:
                return True
            if entry.acl_type.value == "tag" and entry.acl_value in acl_context.tags:
                return True
        return False
