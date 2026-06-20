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

#: Reused installation-global sentinel (C01). KB rows carry it because the KB
#: face has no project scope; memory ``global`` rows carry it too.
WORKSPACE_GLOBAL_PROJECT_ID = "00000000000000000000000000"

#: ``kind`` discriminator values for the unified table.
KIND_KNOWLEDGE_BASE = "knowledge_base"
KIND_MEMORY = "memory"


@dataclass(frozen=True)
class Document:
    """One Markdown file = one ``documents`` row.

    Fields map 1:1 to the unified ``documents`` table. ``metadata`` is the
    per-face JSON blob:

    - KB keys: ``original_filename``, ``original_format``, ``source_sha256``,
      ``converted_at``, ``conversion_engine``.
    - memory keys: ``type``, ``actor``, ``origin_session_id``.
    """

    id: str
    kind: str
    resource_name: str
    path: str
    title: str
    content_sha256: str
    source_mode: str
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    project_id: str = WORKSPACE_GLOBAL_PROJECT_ID
    metadata: dict[str, object] = field(default_factory=dict)
