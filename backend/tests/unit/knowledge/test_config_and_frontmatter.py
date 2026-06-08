"""Unit tests for the substrate configs, embedding config, and frontmatter."""

import pytest
from pydantic import ValidationError

from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.infrastructure.knowledge.frontmatter import (
    body_of,
    render_frontmatter,
    split_frontmatter,
)


def test_kb_config_defaults() -> None:
    c = KnowledgeBaseConfig()
    assert c.enabled_modes == ["keyword", "grep"]
    assert c.default_mode == "keyword"
    assert c.vector_enabled is False


def test_kb_vector_requires_embedding() -> None:
    with pytest.raises(ValidationError, match="embedding is required"):
        KnowledgeBaseConfig(enabled_modes=["keyword", "vector"])


def test_kb_vector_with_embedding_ok() -> None:
    c = KnowledgeBaseConfig(
        enabled_modes=["keyword", "vector"],
        embedding=EmbeddingConfig(
            provider="openai",
            model="text-embedding-3-small",
            credential_ref="ref",
            dimensions=1536,
        ),
    )
    assert c.vector_enabled is True


def test_kb_overlap_bound() -> None:
    with pytest.raises(ValidationError, match="chunk_overlap"):
        KnowledgeBaseConfig(chunk_size=100, chunk_overlap=80)


def test_kb_default_mode_must_be_enabled() -> None:
    with pytest.raises(ValidationError, match="default_mode"):
        KnowledgeBaseConfig(enabled_modes=["grep"], default_mode="keyword")


def test_memory_config_defaults_no_llm() -> None:
    c = MemoryStoreConfig()
    assert c.retrieval_modes == ["grep", "keyword"]
    assert c.max_fact_chars == 8192
    assert c.vector_enabled is False
    assert not hasattr(c, "llm_provider")


def test_memory_vector_requires_embedding_fields() -> None:
    with pytest.raises(ValidationError, match="embedding_provider"):
        MemoryStoreConfig(retrieval_modes=["keyword", "vector"])


def test_memory_to_embedding_config() -> None:
    c = MemoryStoreConfig(
        retrieval_modes=["keyword", "vector"],
        embedding_provider="local",
        embedding_model="bge-m3",
        embedding_dimensions=1024,
    )
    ec = c.to_embedding_config()
    assert ec is not None
    assert ec.provider == "local"
    assert ec.dimensions == 1024


def test_frontmatter_roundtrip() -> None:
    fm = {"name": "deploy", "description": "use make release", "metadata": {"type": "project"}}
    rendered = render_frontmatter(fm, "body text here")
    parsed, body = split_frontmatter(rendered)
    assert parsed["name"] == "deploy"
    assert parsed["metadata"]["type"] == "project"
    assert body.strip() == "body text here"


def test_frontmatter_absent_returns_whole_body() -> None:
    fm, body = split_frontmatter("no frontmatter here")
    assert fm == {}
    assert body == "no frontmatter here"
    assert body_of("no frontmatter here") == "no frontmatter here"
