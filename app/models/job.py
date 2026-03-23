from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.models.common import JobStatus, SyncMode, utcnow


@dataclass(slots=True)
class IndexJob:
    id: str
    source_id: str
    mode: SyncMode
    status: JobStatus
    triggered_by: str
    processed_count: int = 0
    failed_count: int = 0
    error_summary: str | None = None
    snapshot_path: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)
