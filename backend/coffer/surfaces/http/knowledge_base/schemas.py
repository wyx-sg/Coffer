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

from coffer.application.knowledge_base.pipeline_helpers import SourceStatus
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
    # WORKSPACE_GLOBAL sentinel for global KB documents (per-project scope is a
    # later slice); surfaced so the UI can group/scope documents.
    project_id: str
    chunk_count: int = 0
    metadata: dict[str, Any]
    # Absolute path of the normalized markdown on disk (the source of truth) and
    # its containing folder. The in-app viewer is read-only; the pair backs
    # open-in-external-editor / reveal-in-file-manager.
    path: str
    folder_path: str
    created_at: datetime
    updated_at: datetime
    # Per-document embed status surfaced on the documents list/detail. Derived
    # from ``embed_pending`` (``embedding`` while pending, else ``done``) overlaid
    # with any in-flight ``queued``/``running``/``error`` re-embed state. Absent
    # (``None``) when the async batch service is not wired (minimal apps / tests).
    embed_status: str | None = Field(
        default=None,
        description="Per-document embed status: done | embedding | queued | running | error.",
    )

    @classmethod
    def from_domain(
        cls,
        d: Document,
        *,
        chunk_count: int = 0,
        path: str,
        folder_path: str,
        embed_status: str | None = None,
    ) -> DocumentOut:
        return cls(
            id=d.id,
            kind=d.kind,
            resource_name=d.resource_name,
            title=d.title,
            description=d.description,
            source_mode=d.source_mode,
            content_sha256=d.content_sha256,
            project_id=d.project_id,
            chunk_count=chunk_count,
            metadata=dict(d.metadata),
            path=path,
            folder_path=folder_path,
            created_at=d.created_at,
            updated_at=d.updated_at,
            embed_status=embed_status,
        )


class DocumentDetailOut(DocumentOut):
    markdown: str

    @classmethod
    def from_domain_with_body(
        cls,
        d: Document,
        markdown: str,
        *,
        chunk_count: int = 0,
        path: str,
        folder_path: str,
        embed_status: str | None = None,
    ) -> DocumentDetailOut:
        base = DocumentOut.from_domain(
            d,
            chunk_count=chunk_count,
            path=path,
            folder_path=folder_path,
            embed_status=embed_status,
        )
        return cls(**base.model_dump(), markdown=markdown)


class DocumentListOut(BaseModel):
    documents: list[DocumentOut]
    total: int


class DocumentEditRequest(BaseModel):
    markdown: str = Field(min_length=1)


class ReindexResult(BaseModel):
    documents_scanned: int
    documents_reindexed: int
    documents_skipped: int
    # Rows pruned because their markdown file was removed out-of-band.
    documents_removed: int = 0
    # Docs indexed keyword-only because the embedding provider was unavailable
    # (marked ``embed_pending`` so the next scan retries just the embed).
    documents_degraded: int = 0


class SourceStatusOut(BaseModel):
    document_id: str
    title: str
    source_path: str
    status: str


class SourceCheckResponse(BaseModel):
    sources: list[SourceStatusOut]

    @classmethod
    def from_report(cls, report: list[SourceStatus]) -> SourceCheckResponse:
        return cls(
            sources=[
                SourceStatusOut(
                    document_id=s.doc_id,
                    title=s.title,
                    source_path=s.source_path,
                    status=s.status,
                )
                for s in report
            ]
        )


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4096)
    top_k: int = Field(default=5, ge=1, le=20)


class Passage(BaseModel):
    text: str
    document_id: str
    title: str
    score: float
    position: int


class SearchResponse(BaseModel):
    passages: list[Passage]

    @classmethod
    def from_result(cls, result: SearchResult) -> SearchResponse:
        return cls(
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
    # Documents indexed keyword-only because the embedding provider was
    # unavailable (embed retried on the next reconcile). 0 when all are embedded.
    documents_degraded: int = 0
    indexed_modes: list[RetrievalMode]
    disk_bytes: int


class ReembedBatchRequest(BaseModel):
    """Request body for POST /api/v1/knowledge_bases/{name}/documents/reembed-batch.

    Either re-embed an explicit ``document_ids`` set, or set ``all`` to re-embed
    every document still pending an embed (re-embed-all). Already-embedded
    documents are skipped."""

    document_ids: list[str] | None = Field(
        default=None, description="Re-embed these specific documents."
    )
    all: bool = Field(
        default=False,
        description="Re-embed every document still pending an embed (re-embed-all).",
    )


class ReembedBatchResponse(BaseModel):
    """Response for POST /api/v1/knowledge_bases/{name}/documents/reembed-batch."""

    queued: int = Field(description="Newly enqueued documents.")
    skipped: int = Field(description="Skipped — already embedded (nothing to retry).")
    total: int = Field(description="Candidate documents considered.")


class DocumentEmbedStatus(BaseModel):
    """A single in-flight document's re-embed state."""

    document_id: str
    state: str = Field(description="queued | running | error")
    message: str | None = Field(default=None, description="Error detail when state is error.")


class DocumentStatusResponse(BaseModel):
    """Response for GET /api/v1/knowledge_bases/{name}/documents/status.

    Only in-flight documents appear (queued / running / error); a document absent
    from the list is either done or still pending an embed (see the list
    endpoint's ``embed_status``)."""

    statuses: list[DocumentEmbedStatus]
