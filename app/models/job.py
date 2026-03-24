from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.models.common import JobFailureStage, JobStatus, SyncMode, utcnow


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
    failure_stage: JobFailureStage | None = None
    snapshot_path: str | None = None
    checkpoint_before: str | None = None
    checkpoint_after: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)

    @property
    def is_active(self) -> bool:
        return self.status in {JobStatus.PENDING, JobStatus.RUNNING}
