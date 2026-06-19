"""Pydantic schemas matching specs/006-knowledge-base/contracts/api.openapi.yaml.

Hand-written to mirror the OpenAPI wire contract (agents/stack.md "wire-contract
rule"). The KB face exposes a unified ``Document`` (kind-discriminated) plus the
three-mode retrieval surface (grep / keyword / vector).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from coffer.domain.knowledge.document import Document
from coffer.domain.knowledge.retrieval import GrepResult, RetrievalMode, SearchResult
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig

# Names that, while matching ResourceRef's broad ``^[a-zA-Z0-9_.-]+$`` pattern,
# would still resolve to a path-traversal target under the kb_root (CODE22-005).
# Reject dot-only names and any name containing path separators outright.
_KB_NAME_FORBIDDEN_DOTS = re.compile(r"^\.+$")
_KB_NAME_FORBIDDEN_CHARS = re.compile(r"[/\\]")


class KnowledgeBaseCreateRequest(BaseModel):
    name: str
    description: str | None = None
    config: KnowledgeBaseConfig = Field(default_factory=KnowledgeBaseConfig)

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
    # Number of documents in the KB (shown in the knowledge-bases table).
    document_count: int = 0
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListOut(BaseModel):
    knowledge_bases: list[KnowledgeBaseOut]


class DocumentOut(BaseModel):
    id: str
    kind: str
    resource_name: str
    title: str
    description: str | None = None
    source_mode: str
    content_sha256: str
    # Co-management lock (ADR-028): a locked document refuses every mutation.
    locked: bool
    # Document scope (ADR-030/FR-022): the WORKSPACE_GLOBAL sentinel for a global
    # document, or a project ULID for a per-project one. The UI scopes by it.
    project_id: str
    # Recoverable soft-delete (ADR-030): null for a live document; set when in the
    # trash. The trash list (?deleted=true) surfaces it; live reads omit it.
    deleted_at: datetime | None = None
    chunk_count: int = 0
    metadata: dict[str, Any]
    # Absolute path of the normalized markdown on disk (the source of truth) and
    # its containing folder. The in-app viewer is read-only; the pair backs
    # open-in-external-editor / reveal-in-file-manager / copy-path.
    path: str
    folder_path: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(
        cls, d: Document, *, chunk_count: int = 0, path: str, folder_path: str
    ) -> DocumentOut:
        return cls(
            id=d.id,
            kind=d.kind,
            resource_name=d.resource_name,
            title=d.title,
            description=d.description,
            source_mode=d.source_mode,
            content_sha256=d.content_sha256,
            locked=d.locked,
            project_id=d.project_id,
            deleted_at=d.deleted_at,
            chunk_count=chunk_count,
            metadata=dict(d.metadata),
            path=path,
            folder_path=folder_path,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class DocumentDetailOut(DocumentOut):
    markdown: str

    @classmethod
    def from_domain_with_body(
        cls, d: Document, markdown: str, *, chunk_count: int = 0, path: str, folder_path: str
    ) -> DocumentDetailOut:
        base = DocumentOut.from_domain(
            d, chunk_count=chunk_count, path=path, folder_path=folder_path
        )
        return cls(**base.model_dump(), markdown=markdown)


class DocumentListOut(BaseModel):
    documents: list[DocumentOut]
    total: int


class DocumentEditRequest(BaseModel):
    markdown: str = Field(min_length=1)


class DocumentLockRequest(BaseModel):
    # Desired lock state: true freezes the document against all mutation
    # (edit / reconvert / replace / delete); false unlocks it (ADR-028 / FR-021).
    locked: bool


class ReindexResult(BaseModel):
    documents_scanned: int
    documents_reindexed: int
    documents_skipped: int
    # Rows pruned because their markdown file was removed out-of-band.
    documents_removed: int = 0
    # Docs indexed keyword-only because the embedding provider was unavailable
    # (retried on the next scan via the empty-sha sentinel).
    documents_degraded: int = 0


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4096)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: RetrievalMode | None = None
    # Scope (ADR-030/FR-022): omit for global; a project ULID restricts the
    # search to that scope. The keyword/vector index filters at the SQL layer.
    project_id: str | None = None


class Passage(BaseModel):
    text: str
    document_id: str
    title: str
    score: float
    position: int


class SearchResponse(BaseModel):
    mode: RetrievalMode
    fallback: RetrievalMode | None = None
    passages: list[Passage]

    @classmethod
    def from_result(cls, result: SearchResult) -> SearchResponse:
        return cls(
            mode=result.mode,
            fallback=result.fallback,
            passages=[
                Passage(
                    text=p.text,
                    document_id=p.document_id,
                    title=p.title,
                    score=p.score,
                    position=p.position,
                )
                for p in result.passages
            ],
        )


class GrepRequest(BaseModel):
    pattern: str = Field(min_length=1, max_length=1024)
    max_matches: int = Field(default=100, ge=1, le=1000)
    # Scope (ADR-030/FR-022): omit for global; a project ULID greps only that
    # scope's docs/ subtree.
    project_id: str | None = None


class GrepHitOut(BaseModel):
    path: str
    line_number: int
    line: str


class GrepResponse(BaseModel):
    hits: list[GrepHitOut]
    truncated: bool

    @classmethod
    def from_result(cls, result: GrepResult) -> GrepResponse:
        out = [GrepHitOut(path=h.path, line_number=h.line_number, line=h.line) for h in result.hits]
        return cls(hits=out, truncated=result.truncated)


class KnowledgeBaseMetrics(BaseModel):
    document_count: int
    chunk_count: int
    indexed_modes: list[RetrievalMode]
    disk_bytes: int
