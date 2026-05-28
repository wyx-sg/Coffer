"""Unit tests for KnowledgeBaseConfig validation. Pure — no I/O."""

import pytest

from coffer.domain.knowledge_base.config import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_EMBEDDING_MODEL,
    KnowledgeBaseConfig,
)


def test_defaults() -> None:
    c = KnowledgeBaseConfig()
    assert c.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert c.chunk_size == DEFAULT_CHUNK_SIZE
    assert c.chunk_overlap == DEFAULT_CHUNK_OVERLAP


def test_overlap_must_be_at_most_half_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        KnowledgeBaseConfig(chunk_size=256, chunk_overlap=200)


def test_embedding_model_must_look_like_org_slash_name() -> None:
    with pytest.raises(ValueError, match="embedding_model"):
        KnowledgeBaseConfig(embedding_model="just-a-name")


def test_chunk_size_bounds() -> None:
    with pytest.raises(ValueError):
        KnowledgeBaseConfig(chunk_size=8)
    with pytest.raises(ValueError):
        KnowledgeBaseConfig(chunk_size=99999)
