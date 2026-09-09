"""The unified ``Document`` entity, shared by KB and memory and discriminated
by ``kind``.

One ``Document`` is the in-memory view of one Markdown file on disk (the source
of truth). Every SQLite row is derived from it. KB-specific and memory-specific
data live in the free-form ``metadata`` dict so the single entity (and the
single ``documents`` table) serves both faces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

#: Reused installation-global sentinel (C01). The ``global`` scope and every
#: named collection carry it; a project scope carries its own ULID.
WORKSPACE_GLOBAL_PROJECT_ID = "00000000000000000000000000"

#: The single ``kind`` discriminator for the unified table. There is one
#: knowledge kind; which of the three scopes a row belongs to is read from its
#: ``resource_name`` (``domain.knowledge.scope.scope_kind_of``).
KIND_KNOWLEDGE = "knowledge"

#: Max documents scanned/reconciled per store in one ``list_documents`` pass
#: (reindex scan, source-tracking, entry reconcile). A safety bound — NOT an
#: enforced ingest limit; corpora are expected far below it.
DOCUMENT_SCAN_LIMIT = 100_000


#: Which writer owns an indexed row. ``ENTRY`` is what an agent wrote through
#: ``coffer__write``; ``INGEST`` is a file converted into the scope.
DocumentLane = Literal["knowledge", "inbox"]

LANE_ENTRY: DocumentLane = "knowledge"
LANE_INGEST: DocumentLane = "inbox"


@dataclass(frozen=True)
class Document:
    """One Markdown file = one ``documents`` row.

    Fields map 1:1 to the unified ``documents`` table. ``metadata`` is the
    per-face JSON blob:

    - KB keys: ``original_filename``, ``original_format``, ``source_sha256``,
      ``converted_at``, ``conversion_engine``, and the optional ``source_path``
      (the external original's absolute path, set only for path-based ingests
      so its on-disk drift can later be detected).
    - memory keys: ``type``, ``actor``, ``origin_session_id``.

    ``lane`` says which of a scope's two writers owns the row. Both the entry
    reconciler and the ingest scan index into this table under one
    ``(kind, resource_name)``, and the path alone cannot separate them: entries
    live at ``<scope>/knowledge/inbox/<id>.md`` and ingested documents at
    ``<scope>/inbox/<id>.md``, so a match on ``inbox/`` catches both. The row
    carries its own answer instead.
    """

    id: str
    kind: str
    resource_name: str
    path: str
    lane: DocumentLane
    title: str
    content_sha256: str
    source_mode: str
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    project_id: str = WORKSPACE_GLOBAL_PROJECT_ID
    # Index-derived retry state — like ``content_sha256`` it is NOT file-truth
    # (never written to frontmatter): True when the embedding provider was
    # unavailable so the chunks are keyword-only and the next reindex must retry
    # JUST the embed. Recomputed by the reindex routine on every write.
    embed_pending: bool = False
    metadata: dict[str, object] = field(default_factory=dict)
