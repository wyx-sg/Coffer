"""Configuration held inside a ``knowledge`` Resource's ``config``.

The union of what the two former faces actually used. ``memory`` contributed
the write bound and the merged-identity ledger; ``knowledge_base`` contributed
the ingestion parameters. Retrieval settings were already identical on both
sides — the substrate underneath them never was two things.

**No embedding fields.** Both faces carried their own (``embedding_*`` flat on
memory, a nested ``embedding`` block on the KB) and by the time they were
merged neither was read: embedding resolves through the installation-wide
config, and a scope opts into vector search purely by listing the mode. The
dead fields are dropped rather than carried across.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from coffer.domain.knowledge.retrieval import RETRIEVAL_MODES, RetrievalMode

# Bound on one written entry. The per-scope default bounds ordinary agent
# writes; a trusted bulk import of the user's own notes may go up to the hard
# ceiling so a long note is never silently truncated.
DEFAULT_MAX_ENTRY_CHARS = 8192
MAX_ENTRY_CHARS = 32768

# Ingestion defaults (from the knowledge-base face).
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
DEFAULT_MAX_DOC_BYTES = 25 * 1024 * 1024

DEFAULT_RETRIEVAL_MODES: list[RetrievalMode] = ["grep", "keyword"]
DEFAULT_MODE: RetrievalMode = "keyword"


class KnowledgeConfig(BaseModel):
    """Per-scope knowledge settings. All fields are mutable.

    Changing a retrieval or chunking field re-indexes the scope: the files on
    disk are the source of truth (ADR files-as-truth-sqlite-retrieval), so the
    index is always rebuildable and never the thing that must be migrated.
    """

    retrieval_modes: list[RetrievalMode] = Field(
        default_factory=lambda: list(DEFAULT_RETRIEVAL_MODES)
    )
    default_mode: RetrievalMode = DEFAULT_MODE

    # Writes (was memory).
    max_entry_chars: int = Field(default=DEFAULT_MAX_ENTRY_CHARS, ge=64, le=MAX_ENTRY_CHARS)

    # Ingestion (was knowledge_base). Only a scope that ingests files uses
    # these, but they cost nothing on one that does not.
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, ge=64, le=2048)
    chunk_overlap: int = Field(default=DEFAULT_CHUNK_OVERLAP, ge=0)
    max_document_bytes: int = Field(default=DEFAULT_MAX_DOC_BYTES, ge=1024, le=104857600)
    #: When true, ``check-sources`` refreshes documents whose tracked external
    #: original changed, skipping hand-edited ones. NOT a reindex trigger —
    #: toggling it must not re-chunk.
    auto_update_sources: bool = False

    #: Project ids merged INTO this scope (system-managed, never user-set). A
    #: resolve whose computed identity is listed here — and whose own scope no
    #: longer exists — lands here instead of provisioning an empty duplicate.
    merged_identities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> KnowledgeConfig:
        seen: list[RetrievalMode] = []
        for mode in self.retrieval_modes:
            if mode not in RETRIEVAL_MODES:
                raise ValueError(f"unknown retrieval mode: {mode!r}")
            if mode not in seen:
                seen.append(mode)
        if not seen:
            raise ValueError("retrieval_modes must list at least one retrieval mode")
        # Enabling ``vector`` lets the scope fuse, so ``hybrid`` comes along and
        # becomes the default unless the caller chose one explicitly.
        if "vector" in seen and "hybrid" not in seen:
            seen.append("hybrid")
        object.__setattr__(self, "retrieval_modes", seen)
        if "vector" in seen and "default_mode" not in self.model_fields_set:
            object.__setattr__(self, "default_mode", "hybrid")
        if self.default_mode not in seen:
            raise ValueError(f"default_mode {self.default_mode!r} is not in retrieval_modes {seen}")

        if self.chunk_overlap > self.chunk_size // 2:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be <= chunk_size/2 "
                f"({self.chunk_size // 2})"
            )
        return self

    @property
    def vector_enabled(self) -> bool:
        """Whether this scope asks to be searched semantically.

        Whether vector search actually runs also depends on the
        installation-wide embedding config being active — a scope can ask for
        it before an embedder exists, and degrades to keyword until one does.
        """
        return "vector" in self.retrieval_modes or "hybrid" in self.retrieval_modes
