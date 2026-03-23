from __future__ import annotations

from app.models.checkpoint import SyncCheckpoint
from app.models.common import generate_id, utcnow


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
