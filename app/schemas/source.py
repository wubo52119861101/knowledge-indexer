from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.common import SourceType, SyncMode
from app.schemas.job import JobItem


class CreateSourceRequest(BaseModel):
    name: str = Field(min_length=1)
    type: SourceType
    config: dict[str, Any] = Field(default_factory=dict)
    sync_mode: SyncMode = SyncMode.INCREMENTAL
    schedule: str | None = None
    enabled: bool = True


class SourceItem(BaseModel):
    id: str
    name: str
    type: SourceType
    config: dict[str, Any]
    sync_mode: SyncMode
    enabled: bool
    last_sync_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SourceDetail(BaseModel):
    source: SourceItem
    latest_job: JobItem | None = None


class TriggerSyncOptions(BaseModel):
    force_rebuild: bool = False


class TriggerSyncRequest(BaseModel):
    mode: SyncMode = SyncMode.INCREMENTAL
    operator: str = "system"
    options: TriggerSyncOptions = Field(default_factory=TriggerSyncOptions)


class TriggerSyncResponse(BaseModel):
    job_id: str
    status: str
    queued_at: datetime
