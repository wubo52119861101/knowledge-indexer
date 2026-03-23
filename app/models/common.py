from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


class SourceType(StrEnum):
    FILE = "file"
    API = "api"
    POSTGRES = "postgres"


class SyncMode(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"
    REBUILD = "rebuild"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class DocumentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"
    FAILED = "FAILED"


class EmbeddingStatus(StrEnum):
    PENDING = "PENDING"
    DONE = "DONE"
    FAILED = "FAILED"


class AclType(StrEnum):
    USER = "user"
    ROLE = "role"
    DEPARTMENT = "department"
    TAG = "tag"


class AclEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class EvidenceStatus(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"
