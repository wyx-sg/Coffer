"""Wire shapes for the one ``knowledge`` kind — scopes, entries, recall, tidy.

The document-side shapes live in ``document_schemas.py``; the split is purely
the file-size budget. One scope model replaces the two pre-merge ones
(``MemoryStoreOut`` + ``KnowledgeBaseOut``): a scope is a scope whether it holds
entries an agent wrote, documents someone ingested, or both, so the wire stops
asking the caller which of the two it is looking at.

``config`` is the domain :class:`KnowledgeConfig` verbatim. The pre-merge memory
face re-declared it with flat ``embedding_*`` fields; those no longer exist
(embedding resolves through the installation-wide config), so there is nothing
left to re-declare.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from coffer.domain.knowledge.entry import Actor, KnowledgeEntry
from coffer.domain.knowledge.retrieval import RetrievalMode
from coffer.domain.knowledge.scope import GLOBAL_SCOPE_NAME, PROJECT_SCOPE_PREFIX
from coffer.domain.knowledge.scope_config import MAX_ENTRY_CHARS, KnowledgeConfig

#: Which of the three a scope is. Derived from the resource name, never stored.
ScopeKind = Literal["global", "project", "named"]

# Surface-level cap mirrors the maximum ``max_entry_chars`` (32768). The service
# re-validates against the scope's configured limit and emits
# ``MEMORY_REJECTED { reason: "too_long" }`` (→ 422) for a per-scope override
# smaller than this; the schema cap only blocks obvious abuse (multi-MB body).
_MAX_ENTRY_CHARS_SCHEMA_CAP = MAX_ENTRY_CHARS

# Surface cap for a display label — long enough for a sentence, short enough to
# render on one table row.
_MAX_LABEL_CHARS = 200

# Names that, while matching ResourceRef's broad ``^[a-zA-Z0-9_.-]+$`` pattern,
# would still resolve to a path-traversal target under the knowledge root.
_NAME_FORBIDDEN_DOTS = re.compile(r"^\.+$")
_NAME_FORBIDDEN_CHARS = re.compile(r"[/\\]")


# --- scope config -----------------------------------------------------------


class KnowledgeConfigPatch(BaseModel):
    """Only the mutable config fields, all optional; ``None`` is a no-op.

    The union of what the two faces patched, minus the embedding fields that no
    longer exist on :class:`KnowledgeConfig`.
    """

    retrieval_modes: list[RetrievalMode] | None = None
    default_mode: RetrievalMode | None = None
    max_entry_chars: int | None = Field(default=None, ge=64, le=MAX_ENTRY_CHARS)
    chunk_size: int | None = Field(default=None, ge=64, le=2048)
    chunk_overlap: int | None = Field(default=None, ge=0)
    max_document_bytes: int | None = Field(default=None, ge=1024, le=104857600)
    auto_update_sources: bool | None = None


class ScopeLabelPatch(BaseModel):
    """Set or clear a scope's display label. An empty or whitespace-only label
    clears it, reverting to the derived / fallback name."""

    label: str | None = Field(default=None, max_length=_MAX_LABEL_CHARS)


class ScopeCreate(BaseModel):
    """Create a NAMED collection.

    ``global`` and ``project-<ULID>`` auto-provision on first use and are
    rejected here: conjuring one by hand would let a typo'd name masquerade as
    an auto-scope."""

    name: str
    description: str | None = None
    config: KnowledgeConfig = Field(default_factory=KnowledgeConfig)

    @field_validator("name")
    @classmethod
    def _reject_reserved_and_traversal(cls, v: str) -> str:
        if v == GLOBAL_SCOPE_NAME or v.startswith(PROJECT_SCOPE_PREFIX):
            raise ValueError(
                f"{v!r} is an auto-provisioned scope; it is created on first use, not by hand"
            )
        if _NAME_FORBIDDEN_DOTS.match(v):
            raise ValueError("scope name cannot be dot-only (path traversal risk)")
        if _NAME_FORBIDDEN_CHARS.search(v):
            raise ValueError("scope name cannot contain '/' or '\\'")
        if ".." in v:
            raise ValueError("scope name cannot contain '..' (path traversal risk)")
        return v


# --- scope ------------------------------------------------------------------


class ScopeOut(BaseModel):
    """One knowledge scope, whatever kind of material it holds."""

    ref: str
    kind: str
    name: str
    scope: ScopeKind
    #: The project ULID for a project scope, the global sentinel for ``global``,
    #: the collection's own name for a named one.
    project_id: str
    #: Absolute git-root a project scope was provisioned from; ``None`` for
    #: ``global`` and for named collections.
    project_root: str | None = None
    #: User-set display label. When present it is the scope's readable name in
    #: the UI, taking precedence over the derived project-dir basename.
    label: str | None = None
    #: Absolute on-disk directory holding the scope's markdown. The in-app
    #: viewer is read-only; this backs reveal-in-file-manager for the scope.
    scope_dir: str
    description: str | None = None
    config: KnowledgeConfig
    enabled: bool
    #: Notes an agent or the user wrote, under ``notes/``.
    entry_count: int = 0
    #: Documents ingested into ``docs/``.
    document_count: int = 0
    created_at: datetime
    updated_at: datetime


class ScopeListOut(BaseModel):
    scopes: list[ScopeOut]


class ScopeMetrics(BaseModel):
    """The union of what the two faces reported for one scope."""

    entry_count: int
    document_count: int
    chunk_count: int
    #: Documents indexed keyword-only because the embedding provider was
    #: unavailable (the embed is retried on the next reconcile).
    documents_degraded: int = 0
    indexed_modes: list[RetrievalMode]
    disk_bytes: int


# --- entries ----------------------------------------------------------------


class EntryCreate(BaseModel):
    text: str = Field(min_length=1, max_length=_MAX_ENTRY_CHARS_SCHEMA_CAP)
    title: str | None = None
    description: str | None = None


class EntryUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=_MAX_ENTRY_CHARS_SCHEMA_CAP)
    title: str | None = None
    description: str | None = None


class EntryOut(BaseModel):
    id: str
    scope_name: str
    scope: ScopeKind
    title: str
    description: str
    text: str
    actor: Actor
    origin_session_id: str | None = None
    path: str
    #: Absolute path of the entry file's containing folder. The in-app viewer is
    #: read-only; the pair backs open-in-external-editor / reveal-in-file-manager.
    folder_path: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entry(
        cls, e: KnowledgeEntry, *, scope_name: str, scope: ScopeKind, path: str
    ) -> EntryOut:
        return cls(
            id=e.id,
            scope_name=scope_name,
            scope=scope,
            title=e.title,
            description=e.description,
            text=e.body,
            actor=e.actor,
            origin_session_id=e.origin_session_id,
            path=path,
            folder_path=str(Path(path).parent),
            created_at=e.created_at,
            updated_at=e.updated_at,
        )


class EntryListOut(BaseModel):
    entries: list[EntryOut]
    total: int


class ClearResponse(BaseModel):
    cleared: int


# --- recall -----------------------------------------------------------------


RecallScope = Literal["global", "project", "both"]


class RecallRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4096)
    scope: RecallScope = "both"
    top_k: int = Field(default=5, ge=1, le=20)


class RecallHit(BaseModel):
    id: str
    text: str
    score: float
    source: str
    time: datetime


class RecallResponse(BaseModel):
    hits: list[RecallHit]


# --- the tidy pass ----------------------------------------------------------


TidyStatus = Literal["reorganized", "no_model", "empty"]


class OrganizeResponse(BaseModel):
    """Result of one tidy pass over a scope's ``notes/`` lane.

    Everything the pass has to report is a count of note files: how many it
    found, how many it rewrote, and how many prior revisions it moved aside into
    ``.history/`` so an unattended rewrite stays recoverable.

    ``status="no_model"`` (no internal model configured) and ``status="empty"``
    (nothing to tidy) are clean no-ops, not errors."""

    status: TidyStatus
    notes_before: int
    notes_after: int
    notes_written: int
    notes_archived: int
    model: str | None = None
