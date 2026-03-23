from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.models.common import utcnow


@dataclass(slots=True)
class SyncCheckpoint:
    id: str
    source_id: str
    checkpoint_key: str
    checkpoint_value: str
    updated_at: datetime = field(default_factory=utcnow)
