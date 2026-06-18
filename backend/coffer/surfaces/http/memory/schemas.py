"""Pydantic schemas matching specs/007-memory/contracts/api.openapi.yaml.

Hand-written to mirror the OpenAPI wire contract. The memory face is the
writable side of the shared substrate: per-fact markdown files + a regenerated
MEMORY.md, two scopes (global + per-project), no LLM at write time.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from coffer.domain.knowledge.retrieval import RetrievalMode
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.fact import Actor, MemoryFact

Scope = Literal["global", "project"]

# Surface-level cap mirrors the maximum ``max_fact_chars`` (32768). The service
# re-validates against the store's configured limit and emits
# ``MEMORY_REJECTED { reason: "too_long" }`` (→ 422) for a per-store override
# smaller than this; the schema cap only blocks obvious abuse (multi-MB body).
_MAX_FACT_CHARS_SCHEMA_CAP = 32768


# --- store config (full + patch) -------------------------------------------


class MemoryStoreConfigOut(BaseModel):
    """The store config as exposed on the wire (flat embedding fields)."""

    retrieval_modes: list[RetrievalMode]
    default_mode: RetrievalMode
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    embedding_credential_ref: str | None = None
    embedding_dimensions: int
    max_fact_chars: int

    @classmethod
    def from_config(cls, c: MemoryStoreConfig) -> MemoryStoreConfigOut:
        return cls(
            retrieval_modes=list(c.retrieval_modes),
            default_mode=c.default_mode,
            embedding_provider=c.embedding_provider,
            embedding_model=c.embedding_model,
            embedding_base_url=c.embedding_base_url,
            embedding_credential_ref=c.embedding_credential_ref,
            embedding_dimensions=c.embedding_dimensions,
            max_fact_chars=c.max_fact_chars,
        )


class MemoryStoreConfigPatch(BaseModel):
    """Only mutable fields; all optional. ``None`` is a no-op (field untouched)
    rather than a clear — clearing an embedding field is done by omitting it
    from the patch and re-PATCHing the whole config server-side is not needed
    for v1."""

    retrieval_modes: list[RetrievalMode] | None = None
    default_mode: RetrievalMode | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    embedding_credential_ref: str | None = None
    embedding_dimensions: int | None = Field(default=None, ge=1, le=8192)
    max_fact_chars: int | None = Field(default=None, ge=64, le=32768)


class MemoryStoreOut(BaseModel):
    ref: str
    kind: str
    name: str
    scope: Scope
    project_id: str
    # Absolute git-root a project store was provisioned from; ``None`` for the
    # global store (and for project stores provisioned before this was tracked).
    project_root: str | None = None
    # Absolute on-disk directory holding the store's per-fact markdown files.
    # The in-app viewer is read-only; this backs reveal-in-file-manager /
    # copy-path for the whole store.
    store_dir: str
    description: str | None = None
    config: MemoryStoreConfigOut
    enabled: bool
    # Number of facts currently in the store (shown in the stores table).
    fact_count: int = 0
    created_at: datetime
    updated_at: datetime


class MemoryStoreListOut(BaseModel):
    memory_stores: list[MemoryStoreOut]


class MemoryStoreMetrics(BaseModel):
    fact_count: int
    disk_bytes: int


# --- facts ------------------------------------------------------------------


class FactCreate(BaseModel):
    text: str = Field(min_length=1, max_length=_MAX_FACT_CHARS_SCHEMA_CAP)
    name: str | None = None
    description: str | None = None
    type: str | None = None


class FactUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=_MAX_FACT_CHARS_SCHEMA_CAP)
    name: str | None = None
    description: str | None = None
    type: str | None = None


class FactOut(BaseModel):
    id: str
    store_name: str
    scope: Scope
    name: str
    description: str
    text: str
    type: str | None = None
    actor: Actor
    origin_session_id: str | None = None
    path: str
    # Absolute path of the fact file's containing folder (the store dir). The
    # in-app viewer is read-only; the pair backs open-in-external-editor /
    # reveal-in-file-manager / copy-path.
    folder_path: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_fact(cls, f: MemoryFact, *, store_name: str, scope: Scope, path: str) -> FactOut:
        return cls(
            id=f.id,
            store_name=store_name,
            scope=scope,
            name=f.name,
            description=f.description,
            text=f.body,
            type=f.type,
            actor=f.actor,
            origin_session_id=f.origin_session_id,
            path=path,
            folder_path=str(Path(path).parent),
            created_at=f.created_at,
            updated_at=f.updated_at,
        )


class FactListOut(BaseModel):
    facts: list[FactOut]
    total: int


class ClearResponse(BaseModel):
    cleared: int


# --- recall -----------------------------------------------------------------


RecallScope = Literal["global", "project", "both"]


class RecallRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4096)
    scope: RecallScope = "both"
    mode: RetrievalMode | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class RecallHit(BaseModel):
    id: str
    text: str
    score: float
    source: str
    time: datetime


class RecallResponse(BaseModel):
    hits: list[RecallHit]
    mode: RetrievalMode
    fallback: bool = False


# --- projection -------------------------------------------------------------


ProjectionMode = Literal["SYMLINK", "RENDER", "NONE"]


class ProjectionOut(BaseModel):
    agent_ref: str
    projection_mode: ProjectionMode
    target_path: str
    native_memory_disabled: bool
    merged_existing: bool = False


class ProjectionListOut(BaseModel):
    projections: list[ProjectionOut]
