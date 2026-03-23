from __future__ import annotations

from app.models.common import utcnow
from app.models.source import Source


class InMemorySourceRepository:
    def __init__(self) -> None:
        self._sources: dict[str, Source] = {}

    def add(self, source: Source) -> Source:
        self._sources[source.id] = source
        return source

    def get(self, source_id: str) -> Source | None:
        return self._sources.get(source_id)

    def list_all(self) -> list[Source]:
        return list(self._sources.values())

    def touch_sync(self, source_id: str) -> None:
        source = self._sources[source_id]
        source.last_sync_at = utcnow()
        source.updated_at = utcnow()
