from __future__ import annotations

from app.models.chunk import Chunk


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
