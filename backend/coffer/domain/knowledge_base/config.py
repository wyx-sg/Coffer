"""Configuration schema held inside a `knowledge_base` Resource's `config`.

Redesign (spec 006): no LlamaIndex, no HuggingFace model id. Retrieval is the
shared three-mode substrate (grep / keyword / vector); vector is opt-in and
carries a DevPilot-style OpenAI-compatible ``EmbeddingConfig``. All fields are
**mutable** post-creation — changing chunk params re-chunks, changing the
embedding model re-embeds. There is no immutability lock.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.domain.knowledge.retrieval import RETRIEVAL_MODES, RetrievalMode

DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
DEFAULT_MAX_DOC_BYTES = 25 * 1024 * 1024
DEFAULT_ENABLED_MODES: list[RetrievalMode] = ["keyword", "grep"]
DEFAULT_MODE: RetrievalMode = "keyword"


class KnowledgeBaseConfig(BaseModel):
    """Per-KB retrieval settings."""

    enabled_modes: list[RetrievalMode] = Field(default_factory=lambda: list(DEFAULT_ENABLED_MODES))
    default_mode: RetrievalMode = DEFAULT_MODE
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, ge=64, le=2048)
    chunk_overlap: int = Field(default=DEFAULT_CHUNK_OVERLAP, ge=0)
    max_document_bytes: int = Field(default=DEFAULT_MAX_DOC_BYTES, ge=1024, le=104857600)
    embedding: EmbeddingConfig | None = None
    # When true, ``check_sources`` auto-refreshes documents whose tracked
    # external original has changed (skipping hand-edited ones). Off by default;
    # NOT a reindex-triggering field (toggling it must not re-chunk/re-embed).
    auto_update_sources: bool = False

    @model_validator(mode="after")
    def _check_cross_field(self) -> KnowledgeBaseConfig:
        # Overlap must stay <= chunk_size / 2.
        if self.chunk_overlap > self.chunk_size // 2:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be <= chunk_size/2 "
                f"({self.chunk_size // 2})"
            )
        # Deduplicate + validate the mode set.
        seen: list[RetrievalMode] = []
        for mode in self.enabled_modes:
            if mode not in RETRIEVAL_MODES:
                raise ValueError(f"unknown retrieval mode: {mode!r}")
            if mode not in seen:
                seen.append(mode)
        if not seen:
            raise ValueError("enabled_modes must list at least one retrieval mode")
        object.__setattr__(self, "enabled_modes", seen)
        # The default mode must be enabled.
        if self.default_mode not in seen:
            raise ValueError(f"default_mode {self.default_mode!r} is not in enabled_modes {seen}")
        return self

    @property
    def vector_enabled(self) -> bool:
        # Embedding is GLOBAL now (not per-KB): a KB opts into vector by listing
        # the mode; whether vector actually indexes depends on the global
        # embedding config being active. The legacy ``embedding`` field is
        # accepted but ignored.
        return "vector" in self.enabled_modes
