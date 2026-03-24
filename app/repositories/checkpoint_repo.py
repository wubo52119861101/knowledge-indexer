from __future__ import annotations

from typing import Protocol

from app.core.database import PostgresRepositoryBase
from app.models.checkpoint import SyncCheckpoint
from app.models.common import generate_id, utcnow


class CheckpointRepository(Protocol):
    def get(self, source_id: str, checkpoint_key: str) -> SyncCheckpoint | None: ...

    def save(self, source_id: str, checkpoint_key: str, checkpoint_value: str) -> SyncCheckpoint: ...


class InMemoryCheckpointRepository:
    def __init__(self) -> None:
        self._checkpoints: dict[tuple[str, str], SyncCheckpoint] = {}

    def get(self, source_id: str, checkpoint_key: str) -> SyncCheckpoint | None:
        return self._checkpoints.get((source_id, checkpoint_key))

    def save(self, source_id: str, checkpoint_key: str, checkpoint_value: str) -> SyncCheckpoint:
        checkpoint = self._checkpoints.get((source_id, checkpoint_key))
        if checkpoint is None:
            checkpoint = SyncCheckpoint(
                id=generate_id("ckp"),
                source_id=source_id,
                checkpoint_key=checkpoint_key,
                checkpoint_value=checkpoint_value,
            )
        checkpoint.checkpoint_value = checkpoint_value
        checkpoint.updated_at = utcnow()
        self._checkpoints[(source_id, checkpoint_key)] = checkpoint
        return checkpoint


class PostgresCheckpointRepository(PostgresRepositoryBase):
    def get(self, source_id: str, checkpoint_key: str) -> SyncCheckpoint | None:
        row = self._fetchone(
            """
            SELECT id, source_id, checkpoint_key, checkpoint_value, updated_at
            FROM kb_sync_checkpoints
            WHERE source_id = %s AND checkpoint_key = %s
            """,
            (source_id, checkpoint_key),
        )
        if row is None:
            return None
        return self._to_model(row)

    def save(self, source_id: str, checkpoint_key: str, checkpoint_value: str) -> SyncCheckpoint:
        checkpoint = self.get(source_id, checkpoint_key)
        checkpoint_id = checkpoint.id if checkpoint else generate_id("ckp")
        timestamp = utcnow()
        row = self._fetchone_write(
            """
            INSERT INTO kb_sync_checkpoints (id, source_id, checkpoint_key, checkpoint_value, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_id, checkpoint_key)
            DO UPDATE SET checkpoint_value = EXCLUDED.checkpoint_value,
                          updated_at = EXCLUDED.updated_at
            RETURNING id, source_id, checkpoint_key, checkpoint_value, updated_at
            """,
            (checkpoint_id, source_id, checkpoint_key, checkpoint_value, timestamp),
        )
        if row is None:
            raise RuntimeError("failed to persist checkpoint")
        return self._to_model(row)

    def _to_model(self, row: dict) -> SyncCheckpoint:
        return SyncCheckpoint(
            id=row["id"],
            source_id=row["source_id"],
            checkpoint_key=row["checkpoint_key"],
            checkpoint_value=row["checkpoint_value"],
            updated_at=row["updated_at"],
        )
