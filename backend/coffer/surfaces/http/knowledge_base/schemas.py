"""Pydantic schemas matching specs/006-knowledge-base/contracts/api.openapi.yaml."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from coffer.domain.knowledge_base.config import KnowledgeBaseConfig

# Names that, while matching ResourceRef's broad ``^[a-zA-Z0-9_.-]+$`` pattern,
# would still resolve to a path-traversal target under the kb_root (CODE22-005).
# Reject dot-only names and any name containing path separators outright.
_KB_NAME_FORBIDDEN_DOTS = re.compile(r"^\.+$")
_KB_NAME_FORBIDDEN_CHARS = re.compile(r"[/\\]")


class KnowledgeBaseCreateRequest(BaseModel):
    name: str
    description: str | None = None
    config: KnowledgeBaseConfig

    @field_validator("name")
    @classmethod
    def _reject_path_traversal_names(cls, v: str) -> str:
        if _KB_NAME_FORBIDDEN_DOTS.match(v):
            raise ValueError("knowledge_base name cannot be dot-only (path traversal risk)")
        if _KB_NAME_FORBIDDEN_CHARS.search(v):
            raise ValueError("knowledge_base name cannot contain '/' or '\\'")
        if ".." in v:
            raise ValueError("knowledge_base name cannot contain '..' (path traversal risk)")
        return v


class KnowledgeBaseOut(BaseModel):
    ref: str
    kind: str
    name: str
    description: str | None = None
    config: KnowledgeBaseConfig
    enabled: bool
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListOut(BaseModel):
    knowledge_bases: list[KnowledgeBaseOut]


class DocumentOut(BaseModel):
    id: str
    kb_name: str
    filename: str
    extension: str
    size_bytes: int
    sha256: str
    chunk_count: int
    ingested_at: datetime


class DocumentDetailOut(DocumentOut):
    text: str


class DocumentListOut(BaseModel):
    documents: list[DocumentOut]
    total: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4096)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchHit(BaseModel):
    text: str
    document_id: str
    filename: str
    score: float
    position: int


class SearchResponse(BaseModel):
    hits: list[SearchHit]


class KnowledgeBaseMetrics(BaseModel):
    document_count: int
    disk_bytes: int
