from __future__ import annotations

from app.models.common import DocumentStatus, utcnow
from app.models.document import Document


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents_by_id: dict[str, Document] = {}
        self._document_key_map: dict[tuple[str, str], str] = {}

    def upsert(self, document: Document) -> Document:
        key = (document.source_id, document.external_doc_id)
        existing_id = self._document_key_map.get(key)
        if existing_id:
            existing = self._documents_by_id[existing_id]
            document.id = existing.id
            document.version = existing.version + 1
            document.created_at = existing.created_at
            document.updated_at = utcnow()
        self._document_key_map[key] = document.id
        self._documents_by_id[document.id] = document
        return document

    def get(self, document_id: str) -> Document | None:
        return self._documents_by_id.get(document_id)

    def list_all(self) -> list[Document]:
        return list(self._documents_by_id.values())

    def list_by_source(self, source_id: str) -> list[Document]:
        return [document for document in self._documents_by_id.values() if document.source_id == source_id]

    def mark_missing_as_deleted(self, source_id: str, active_external_doc_ids: set[str]) -> list[Document]:
        removed_documents: list[Document] = []
        for document in self.list_by_source(source_id):
            if document.external_doc_id in active_external_doc_ids:
                continue
            if document.status is DocumentStatus.DELETED:
                continue
            document.status = DocumentStatus.DELETED
            document.updated_at = utcnow()
            removed_documents.append(document)
        return removed_documents
