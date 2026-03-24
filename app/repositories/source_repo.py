from __future__ import annotations

from typing import Protocol

from app.core.database import PostgresRepositoryBase, mask_sensitive_data
from app.models.common import utcnow
from app.models.source import Source


class SourceRepository(Protocol):
    def add(self, source: Source) -> Source: ...

    def get(self, source_id: str) -> Source | None: ...

    def list_all(self) -> list[Source]: ...

    def touch_sync(self, source_id: str) -> None: ...


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


class PostgresSourceRepository(PostgresRepositoryBase):
    def add(self, source: Source) -> Source:
        self._execute(
            """
            INSERT INTO kb_sources (
                id, name, type, config_json, config_masked_json, sync_mode,
                enabled, last_sync_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source.id,
                source.name,
                source.type.value,
                source.config,
                mask_sensitive_data(source.config),
                source.sync_mode.value,
                source.enabled,
                source.last_sync_at,
                source.created_at,
                source.updated_at,
            ),
        )
        return source

    def get(self, source_id: str) -> Source | None:
        row = self._fetchone(
            """
            SELECT id, name, type, config_json, sync_mode, enabled, last_sync_at, created_at, updated_at
            FROM kb_sources
            WHERE id = %s
            """,
            (source_id,),
        )
        if row is None:
            return None
        return self._to_model(row)

    def list_all(self) -> list[Source]:
        rows = self._fetchall(
            """
            SELECT id, name, type, config_json, sync_mode, enabled, last_sync_at, created_at, updated_at
            FROM kb_sources
            ORDER BY created_at ASC
            """
        )
        return [self._to_model(row) for row in rows]

    def touch_sync(self, source_id: str) -> None:
        timestamp = utcnow()
        self._execute(
            """
            UPDATE kb_sources
            SET last_sync_at = %s, updated_at = %s
            WHERE id = %s
            """,
            (timestamp, timestamp, source_id),
        )

    def _to_model(self, row: dict) -> Source:
        from app.models.common import SourceType, SyncMode

        return Source(
            id=row["id"],
            name=row["name"],
            type=SourceType(row["type"]),
            config=dict(row["config_json"] or {}),
            sync_mode=SyncMode(row["sync_mode"]),
            enabled=bool(row["enabled"]),
            last_sync_at=row["last_sync_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
