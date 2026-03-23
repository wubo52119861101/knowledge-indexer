from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.common import JobStatus, SyncMode


class JobItem(BaseModel):
    id: str
    source_id: str
    mode: SyncMode
    status: JobStatus
    triggered_by: str
    processed_count: int
    failed_count: int
    error_summary: str | None = None
    snapshot_path: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
