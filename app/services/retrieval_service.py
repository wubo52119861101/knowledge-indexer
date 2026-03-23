from __future__ import annotations

from app.core.utils import cosine_similarity
from app.models.common import DocumentStatus
from app.models.document import Document, DocumentAcl
from app.repositories.chunk_repo import InMemoryChunkRepository
from app.repositories.document_repo import InMemoryDocumentRepository
from app.repositories.source_repo import InMemorySourceRepository
from app.schemas.retrieval import AclContext, CitationItem, SearchDocument, SearchFilters, SearchItem, SearchSource
from app.services.embedding_service import HashEmbeddingService


class RetrievalService:
    def __init__(
        self,
        source_repo: InMemorySourceRepository,
        document_repo: InMemoryDocumentRepository,
        chunk_repo: InMemoryChunkRepository,
        embedding_service: HashEmbeddingService,
        min_score_threshold: float = 0.0,
    ) -> None:
        self.source_repo = source_repo
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.embedding_service = embedding_service
        self.min_score_threshold = min_score_threshold

    def search(
        self,
        query: str,
        top_k: int,
        filters: SearchFilters,
        acl_context: AclContext,
    ) -> list[SearchItem]:
        query_embedding = self.embedding_service.embed(query)
        scored_items: list[tuple[float, SearchItem]] = []

        for chunk in self.chunk_repo.list_all():
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

            score = cosine_similarity(query_embedding, chunk.embedding)
            if score < self.min_score_threshold:
                continue
            scored_items.append(
                (
                    score,
                    SearchItem(
                        chunk_id=chunk.id,
                        document_id=document.id,
                        score=round(score, 4),
                        content=chunk.content,
                        source=SearchSource(source_id=source.id, source_type=source.type.value),
                        document=SearchDocument(title=document.title, external_id=document.external_doc_id),
                        citation=CitationItem(doc_title=document.title, chunk_index=chunk.chunk_index),
                    ),
                )
            )

        scored_items.sort(key=lambda item: item[0], reverse=True)
        return [item for _, item in scored_items[:top_k]]

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
