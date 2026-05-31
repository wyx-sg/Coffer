"""Pydantic schemas matching specs/007-memory/contracts/api.openapi.yaml."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.record import Actor


class MemoryStoreCreateRequest(BaseModel):
    name: str
    description: str | None = None
    config: MemoryStoreConfig


class MemoryStoreOut(BaseModel):
    ref: str
    kind: str
    name: str
    description: str | None = None
    config: MemoryStoreConfig
    enabled: bool
    created_at: datetime
    updated_at: datetime


class MemoryStoreListOut(BaseModel):
    memory_stores: list[MemoryStoreOut]


class MemoryStoreMetricsOut(BaseModel):
    memory_count: int
    disk_bytes: int


# Surface-level cap mirrors the default ``max_memory_chars`` in
# :class:`MemoryStoreConfig` (spec 007 FR-005). Per-store overrides may be
# *smaller* than this; the service re-validates against the store's
# configured limit and emits ``MEMORY_REJECTED { reason: "too_long" }``.
# The schema cap exists so an obvious abuse (multi-megabyte body) is
# rejected by FastAPI before it reaches the service layer.
_MAX_MEMORY_CHARS_SCHEMA_CAP = 8192


class MemoryCreate(BaseModel):
    text: str = Field(min_length=1, max_length=_MAX_MEMORY_CHARS_SCHEMA_CAP)


class MemoryUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=_MAX_MEMORY_CHARS_SCHEMA_CAP)


class MemoryOut(BaseModel):
    id: str
    store_name: str
    text: str
    actor: Actor
    created_at: datetime
    updated_at: datetime


class MemoryListOut(BaseModel):
    memories: list[MemoryOut]
    total: int


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4096)
    top_k: int = Field(default=5, ge=1, le=20)


class MemorySearchHit(BaseModel):
    id: str
    text: str
    score: float
    created_at: datetime


class MemorySearchResponse(BaseModel):
    hits: list[MemorySearchHit]


class MemoryClearResponse(BaseModel):
    cleared: int
