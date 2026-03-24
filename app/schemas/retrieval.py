from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.common import EvidenceStatus, PipelineEngineInfo


class AclContext(BaseModel):
    user_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class SearchFilters(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    doc_types: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    acl_context: AclContext = Field(default_factory=AclContext)


class SearchSource(BaseModel):
    source_id: str
    source_type: str


class SearchDocument(BaseModel):
    title: str
    external_id: str


class CitationItem(BaseModel):
    doc_title: str
    chunk_index: int


class SearchItem(BaseModel):
    chunk_id: str
    document_id: str
    score: float
    content: str
    source: SearchSource
    document: SearchDocument
    citation: CitationItem


class SearchResponseData(BaseModel):
    items: list[SearchItem]
    pipeline_engine: PipelineEngineInfo
    rerank_applied: bool = False


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    acl_context: AclContext = Field(default_factory=AclContext)


class AskResponseData(BaseModel):
    answer: str
    citations: list[SearchItem]
    evidence_status: EvidenceStatus
    reason: str | None = None
    answer_mode: Literal["generated", "fallback"] = "fallback"
    pipeline_engine: PipelineEngineInfo
    rerank_applied: bool = False
