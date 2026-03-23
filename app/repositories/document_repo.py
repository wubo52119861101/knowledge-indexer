from __future__ import annotations

from typing import Protocol

from app.core.database import PostgresRepositoryBase
from app.models.common import AclEffect, AclType, DocumentStatus, utcnow
from app.models.document import Document, DocumentAcl


class DocumentRepository(Protocol):
    def upsert(self, document: Document) -> Document: ...

    def get(self, document_id: str) -> Document | None: ...

    def list_all(self) -> list[Document]: ...

    def list_by_source(self, source_id: str) -> list[Document]: ...

    def mark_missing_as_deleted(self, source_id: str, active_external_doc_ids: set[str]) -> list[Document]: ...


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


class PostgresDocumentRepository(PostgresRepositoryBase):
    def upsert(self, document: Document) -> Document:
        timestamp = utcnow()
        row = self._fetchone_write(
            """
            INSERT INTO kb_documents (
                id, source_id, external_doc_id, title, content_text, content_hash,
                doc_type, metadata_json, acl_json, status, version, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, external_doc_id)
            DO UPDATE SET title = EXCLUDED.title,
                          content_text = EXCLUDED.content_text,
                          content_hash = EXCLUDED.content_hash,
                          doc_type = EXCLUDED.doc_type,
                          metadata_json = EXCLUDED.metadata_json,
                          acl_json = EXCLUDED.acl_json,
                          status = EXCLUDED.status,
                          version = kb_documents.version + 1,
                          updated_at = EXCLUDED.updated_at
            RETURNING id, source_id, external_doc_id, title, content_text, content_hash,
                      doc_type, metadata_json, acl_json, status, version, created_at, updated_at
            """,
            (
                document.id,
                document.source_id,
                document.external_doc_id,
                document.title,
                document.content_text,
                document.content_hash,
                document.doc_type,
                document.metadata,
                [self._acl_to_dict(entry) for entry in document.acl_entries],
                document.status.value,
                document.version,
                document.created_at,
                timestamp,
            ),
        )
        if row is None:
            raise RuntimeError("failed to upsert document")
        return self._to_model(row)

    def get(self, document_id: str) -> Document | None:
        row = self._fetchone(
            """
            SELECT id, source_id, external_doc_id, title, content_text, content_hash,
                   doc_type, metadata_json, acl_json, status, version, created_at, updated_at
            FROM kb_documents
            WHERE id = %s
            """,
            (document_id,),
        )
        if row is None:
            return None
        return self._to_model(row)

    def list_all(self) -> list[Document]:
        rows = self._fetchall(
            """
            SELECT id, source_id, external_doc_id, title, content_text, content_hash,
                   doc_type, metadata_json, acl_json, status, version, created_at, updated_at
            FROM kb_documents
            ORDER BY created_at ASC
            """
        )
        return [self._to_model(row) for row in rows]

    def list_by_source(self, source_id: str) -> list[Document]:
        rows = self._fetchall(
            """
            SELECT id, source_id, external_doc_id, title, content_text, content_hash,
                   doc_type, metadata_json, acl_json, status, version, created_at, updated_at
            FROM kb_documents
            WHERE source_id = %s
            ORDER BY created_at ASC
            """,
            (source_id,),
        )
        return [self._to_model(row) for row in rows]

    def mark_missing_as_deleted(self, source_id: str, active_external_doc_ids: set[str]) -> list[Document]:
        removed_documents: list[Document] = []
        for document in self.list_by_source(source_id):
            if document.external_doc_id in active_external_doc_ids:
                continue
            if document.status is DocumentStatus.DELETED:
                continue
            updated = self._fetchone_write(
                """
                UPDATE kb_documents
                SET status = %s, updated_at = %s
                WHERE id = %s
                RETURNING id, source_id, external_doc_id, title, content_text, content_hash,
                          doc_type, metadata_json, acl_json, status, version, created_at, updated_at
                """,
                (DocumentStatus.DELETED.value, utcnow(), document.id),
            )
            if updated is not None:
                removed_documents.append(self._to_model(updated))
        return removed_documents

    def _to_model(self, row: dict) -> Document:
        return Document(
            id=row["id"],
            source_id=row["source_id"],
            external_doc_id=row["external_doc_id"],
            title=row["title"],
            content_text=row["content_text"],
            content_hash=row["content_hash"],
            doc_type=row["doc_type"],
            metadata=dict(row["metadata_json"] or {}),
            status=DocumentStatus(row["status"]),
            version=int(row["version"]),
            acl_entries=[self._acl_from_dict(item) for item in (row["acl_json"] or [])],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _acl_to_dict(self, acl: DocumentAcl) -> dict[str, str]:
        return {"acl_type": acl.acl_type.value, "acl_value": acl.acl_value, "effect": acl.effect.value}

    def _acl_from_dict(self, payload: dict) -> DocumentAcl:
        return DocumentAcl(
            acl_type=AclType(payload["acl_type"]),
            acl_value=payload["acl_value"],
            effect=AclEffect(payload.get("effect", AclEffect.ALLOW.value)),
        )
