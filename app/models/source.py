from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.common import SourceType, SyncMode, utcnow


@dataclass(slots=True)
class Source:
    id: str
    name: str
    type: SourceType
    config: dict[str, Any]
    sync_mode: SyncMode
    enabled: bool = True
    last_sync_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
