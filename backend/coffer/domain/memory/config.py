"""Configuration schema held inside a `memory` Resource's `config`.

Redesign (spec 007): no mem0, no LLM at write time. Shares the retrieval +
embedding config shape with the KB face. Embedding fields are flat (matching
the data-model table) rather than a nested ``EmbeddingConfig`` so the memory
surface stays a thin form. All fields are mutable.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from coffer.domain.knowledge.retrieval import RETRIEVAL_MODES, RetrievalMode

DEFAULT_MAX_FACT_CHARS = 8192
# Hard ceiling on a single fact's length. The per-store default bounds ordinary
# agent ``remember`` writes; trusted bulk imports of a user's own existing memory
# may write up to this ceiling so a long note is never truncated or dropped.
MAX_FACT_CHARS = 32768
DEFAULT_RETRIEVAL_MODES: list[RetrievalMode] = ["grep", "keyword"]
DEFAULT_MODE: RetrievalMode = "keyword"
DEFAULT_EMBEDDING_DIMENSIONS = 768


class MemoryStoreConfig(BaseModel):
    """Per-store memory settings. No ``llm_provider`` — the agent writes a clean
    fact directly."""

    retrieval_modes: list[RetrievalMode] = Field(
        default_factory=lambda: list(DEFAULT_RETRIEVAL_MODES)
    )
    default_mode: RetrievalMode = DEFAULT_MODE
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    embedding_credential_ref: str | None = None
    embedding_dimensions: int = Field(default=DEFAULT_EMBEDDING_DIMENSIONS, ge=1, le=8192)
    max_fact_chars: int = Field(default=DEFAULT_MAX_FACT_CHARS, ge=64, le=MAX_FACT_CHARS)

    @model_validator(mode="after")
    def _check(self) -> MemoryStoreConfig:
        seen: list[RetrievalMode] = []
        for mode in self.retrieval_modes:
            if mode not in RETRIEVAL_MODES:
                raise ValueError(f"unknown retrieval mode: {mode!r}")
            if mode not in seen:
                seen.append(mode)
        if not seen:
            raise ValueError("retrieval_modes must list at least one retrieval mode")
        # Mirror the KB face (knowledge_base/config.py): enabling ``vector`` lets
        # the store fuse, so ``hybrid`` is added automatically and becomes the
        # default (unless the caller explicitly chose one) — keeps the shared
        # substrate coherent. ``keyword`` stays the default when vector is off.
        if "vector" in seen and "hybrid" not in seen:
            seen.append("hybrid")
        object.__setattr__(self, "retrieval_modes", seen)
        if "vector" in seen and "default_mode" not in self.model_fields_set:
            object.__setattr__(self, "default_mode", "hybrid")
        if self.default_mode not in seen:
            raise ValueError(f"default_mode {self.default_mode!r} is not in retrieval_modes {seen}")
        return self

    @property
    def vector_enabled(self) -> bool:
        # Embedding is GLOBAL now (not per-store): a store opts into vector by
        # listing the mode (or ``hybrid``, which fuses vector); whether vector
        # actually indexes depends on the global embedding config being active.
        # The legacy ``embedding_*`` fields are accepted but ignored.
        return "vector" in self.retrieval_modes or "hybrid" in self.retrieval_modes
