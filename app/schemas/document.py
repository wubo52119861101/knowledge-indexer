from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.common import AclEffect, AclType


class AclEntryPayload(BaseModel):
    type: AclType
    value: str = Field(min_length=1)
    effect: AclEffect = AclEffect.ALLOW


class DocumentPayload(BaseModel):
    external_doc_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str = ""
    doc_type: str = "text"
    metadata: dict[str, Any] = Field(default_factory=dict)
    acl: list[AclEntryPayload] = Field(default_factory=list)
    deleted: bool = False
    checkpoint_value: str | None = None
