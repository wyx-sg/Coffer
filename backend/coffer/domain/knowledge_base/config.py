"""Configuration schema held inside a `knowledge_base` Resource's `config` field."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
DEFAULT_MAX_DOC_BYTES = 25 * 1024 * 1024

# Search strategy for a KB:
# - "keyword": plain text search over ingested documents — no embedding model,
#   no model download, works like searching files. The default so a KB is
#   usable the moment it is created.
# - "semantic": LlamaIndex vector search using ``embedding_model`` (downloaded
#   on first ingest). Opt-in for similarity / meaning-based retrieval.
SearchMode = Literal["keyword", "semantic"]
DEFAULT_SEARCH_MODE: SearchMode = "keyword"


class KnowledgeBaseConfig(BaseModel):
    """Per-KB settings. Immutable post-creation except `max_document_bytes`."""

    search_mode: SearchMode = DEFAULT_SEARCH_MODE
    embedding_model: str = Field(default=DEFAULT_EMBEDDING_MODEL, min_length=1)
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, ge=64, le=2048)
    chunk_overlap: int = Field(default=DEFAULT_CHUNK_OVERLAP, ge=0, le=1024)
    max_document_bytes: int = Field(default=DEFAULT_MAX_DOC_BYTES, ge=1024, le=100 * 1024 * 1024)

    @field_validator("embedding_model")
    @classmethod
    def _embedding_model_shape(cls, v: str) -> str:
        # HuggingFace identifiers look like `org/name`; we don't whitelist
        # specific models, just reject obvious garbage.
        if "/" not in v or v.startswith("/") or v.endswith("/"):
            raise ValueError(
                "embedding_model must look like 'org/model-name' (e.g. 'BAAI/bge-small-en-v1.5')"
            )
        return v

    def model_post_init(self, __context: object) -> None:
        # Cross-field rule: Pydantic v2's per-field `info.data` ordering is not
        # reliable, so the "overlap ≤ chunk_size / 2" check lives here. The
        # absolute bounds are enforced by the `Field` constraints above.
        if self.chunk_overlap > self.chunk_size // 2:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be ≤ chunk_size/2 "
                f"({self.chunk_size // 2})"
            )
