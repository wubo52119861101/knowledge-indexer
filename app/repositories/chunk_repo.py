from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from app.core.database import PostgresRepositoryBase, from_pgvector, to_pgvector_literal
from app.core.utils import cosine_similarity
from app.models.chunk import Chunk
from app.models.common import EmbeddingStatus
from app.schemas.retrieval import SearchFilters


@dataclass(slots=True)
class ChunkSearchCandidate:
    chunk: Chunk
    score: float


class ChunkRepository(Protocol):
    def replace_for_document(self, document_id: str, chunks: list[Chunk]) -> list[Chunk]: ...

    def list_all(self) -> list[Chunk]: ...

    def list_by_document(self, document_id: str) -> list[Chunk]: ...

    def search_candidates(self, query_embedding: list[float], filters: SearchFilters, limit: int) -> list[ChunkSearchCandidate]: ...


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

    def search_candidates(self, query_embedding: list[float], filters: SearchFilters, limit: int) -> list[ChunkSearchCandidate]:
        candidates: list[ChunkSearchCandidate] = []
        for chunk in self.list_all():
            if not self._match_filters(chunk, filters):
                continue
            candidates.append(
                ChunkSearchCandidate(
                    chunk=chunk,
                    score=cosine_similarity(query_embedding, chunk.embedding),
                )
            )
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:limit]

    def _match_filters(self, chunk: Chunk, filters: SearchFilters) -> bool:
        if filters.source_ids and chunk.metadata.get("source_id") not in filters.source_ids:
            return False
        if filters.doc_types and chunk.metadata.get("doc_type") not in filters.doc_types:
            return False
        for key, value in filters.metadata.items():
            if chunk.metadata.get(key) != value:
                return False
        return True


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

    def search_candidates(self, query_embedding: list[float], filters: SearchFilters, limit: int) -> list[ChunkSearchCandidate]:
        if limit <= 0:
            return []

        conditions = ["embedding_status = %s"]
        params: list[object] = [EmbeddingStatus.DONE.value]

        if filters.source_ids:
            placeholders = ", ".join(["%s"] * len(filters.source_ids))
            conditions.append(f"metadata_json ->> 'source_id' IN ({placeholders})")
            params.extend(filters.source_ids)
        if filters.doc_types:
            placeholders = ", ".join(["%s"] * len(filters.doc_types))
            conditions.append(f"metadata_json ->> 'doc_type' IN ({placeholders})")
            params.extend(filters.doc_types)
        if filters.metadata:
            conditions.append("metadata_json @> %s::jsonb")
            params.append(json.dumps(filters.metadata, ensure_ascii=False))

        vector_literal = to_pgvector_literal(query_embedding)
        rows = self._fetchall(
            f"""
            SELECT id, document_id, chunk_index, content, summary,
                   token_count, metadata_json, embedding, embedding_status,
                   created_at, updated_at,
                   1 - (embedding <=> %s::vector) AS score
            FROM kb_chunks
            WHERE {' AND '.join(conditions)}
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s
            """,
            (vector_literal, *params, vector_literal, limit),
        )
        return [
            ChunkSearchCandidate(
                chunk=self._to_model(row),
                score=float(row["score"]),
            )
            for row in rows
        ]

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
