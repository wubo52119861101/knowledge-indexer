from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.common import EmbeddingStatus, utcnow


@dataclass(slots=True)
class Chunk:
    id: str
    document_id: str
    chunk_index: int
    content: str
    summary: str | None
    token_count: int
    metadata: dict[str, Any]
    embedding: list[float] = field(default_factory=list)
    embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
