from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.common import AclEffect, AclType, DocumentStatus, utcnow


@dataclass(slots=True)
class DocumentAcl:
    acl_type: AclType
    acl_value: str
    effect: AclEffect = AclEffect.ALLOW


@dataclass(slots=True)
class Document:
    id: str
    source_id: str
    external_doc_id: str
    title: str
    content_text: str
    content_hash: str
    doc_type: str
    metadata: dict[str, Any]
    status: DocumentStatus = DocumentStatus.ACTIVE
    version: int = 1
    acl_entries: list[DocumentAcl] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
