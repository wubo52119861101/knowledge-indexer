from __future__ import annotations

from typing import Protocol

from app.core.database import PostgresRepositoryBase, from_pgvector, to_pgvector_literal
from app.models.chunk import Chunk
from app.models.common import EmbeddingStatus


class ChunkRepository(Protocol):
    def replace_for_document(self, document_id: str, chunks: list[Chunk]) -> list[Chunk]: ...

    def list_all(self) -> list[Chunk]: ...

    def list_by_document(self, document_id: str) -> list[Chunk]: ...


class InMemoryChunkRepository:
    def __init__(self) -> None:
        self._chunks_by_id: dict[str, Chunk] = {}
        self._document_chunk_ids: dict[str, list[str]] = {}

    def replace_for_document(self, document_id: str, chunks: list[Chunk]) -> list[Chunk]:
        for chunk_id in self._document_chunk_ids.get(document_id, []):
            self._chunks_by_id.pop(chunk_id, None)
        self._document_chunk_ids[document_id] = [chunk.id for chunk in chunks]
        for chunk in chunks:
            self._chunks_by_id[chunk.id] = chunk
        return chunks

    def list_all(self) -> list[Chunk]:
        return list(self._chunks_by_id.values())

    def list_by_document(self, document_id: str) -> list[Chunk]:
        chunk_ids = self._document_chunk_ids.get(document_id, [])
        return [self._chunks_by_id[chunk_id] for chunk_id in chunk_ids]


class PostgresChunkRepository(PostgresRepositoryBase):
    def replace_for_document(self, document_id: str, chunks: list[Chunk]) -> list[Chunk]:
        with self.connection_factory() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM kb_chunks WHERE document_id = %s", (document_id,))
                    for chunk in chunks:
                        cursor.execute(
                            """
                            INSERT INTO kb_chunks (
                                id, document_id, chunk_index, content, summary,
                                token_count, metadata_json, embedding, embedding_status,
                                created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s)
                            """,
                            (
                                chunk.id,
                                chunk.document_id,
                                chunk.chunk_index,
                                chunk.content,
                                chunk.summary,
                                chunk.token_count,
                                chunk.metadata,
                                to_pgvector_literal(chunk.embedding),
                                chunk.embedding_status.value,
                                chunk.created_at,
                                chunk.updated_at,
                            ),
                        )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return chunks

    def list_all(self) -> list[Chunk]:
        rows = self._fetchall(
            """
            SELECT id, document_id, chunk_index, content, summary,
                   token_count, metadata_json, embedding, embedding_status,
                   created_at, updated_at
            FROM kb_chunks
            ORDER BY created_at ASC, chunk_index ASC
            """
        )
        return [self._to_model(row) for row in rows]

    def list_by_document(self, document_id: str) -> list[Chunk]:
        rows = self._fetchall(
            """
            SELECT id, document_id, chunk_index, content, summary,
                   token_count, metadata_json, embedding, embedding_status,
                   created_at, updated_at
            FROM kb_chunks
            WHERE document_id = %s
            ORDER BY chunk_index ASC
            """,
            (document_id,),
        )
        return [self._to_model(row) for row in rows]

    def _to_model(self, row: dict) -> Chunk:
        return Chunk(
            id=row["id"],
            document_id=row["document_id"],
            chunk_index=int(row["chunk_index"]),
            content=row["content"],
            summary=row["summary"],
            token_count=int(row["token_count"]),
            metadata=dict(row["metadata_json"] or {}),
            embedding=from_pgvector(row["embedding"]),
            embedding_status=EmbeddingStatus(row["embedding_status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
