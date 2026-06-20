"""Unit tests for the substrate configs, embedding config, and frontmatter."""

import pytest
from pydantic import ValidationError

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


def test_kb_vector_enabled_by_mode_only() -> None:
    # Embedding is GLOBAL now: listing the mode enables vector; no per-KB
    # embedding config is required.
    assert KnowledgeBaseConfig(enabled_modes=["keyword", "vector"]).vector_enabled is True


def test_kb_overlap_bound() -> None:
    with pytest.raises(ValidationError, match="chunk_overlap"):
        KnowledgeBaseConfig(chunk_size=100, chunk_overlap=80)


def test_kb_default_mode_must_be_enabled() -> None:
    with pytest.raises(ValidationError, match="default_mode"):
        KnowledgeBaseConfig(enabled_modes=["grep"], default_mode="keyword")


def test_kb_enabling_vector_auto_enables_hybrid_and_defaults_to_it() -> None:
    # Enabling vector adds hybrid to the set automatically and makes hybrid the
    # default (vector-enabled KBs get RRF fusion by default).
    c = KnowledgeBaseConfig(enabled_modes=["keyword", "grep", "vector"])
    assert "hybrid" in c.enabled_modes
    assert c.default_mode == "hybrid"
    assert c.vector_enabled is True


def test_kb_explicit_default_mode_overrides_hybrid_auto_default() -> None:
    # A caller who explicitly sets default_mode keeps it (no silent override).
    c = KnowledgeBaseConfig(enabled_modes=["keyword", "grep", "vector"], default_mode="keyword")
    assert c.default_mode == "keyword"
    assert "hybrid" in c.enabled_modes


def test_kb_keyword_stays_default_when_vector_off() -> None:
    c = KnowledgeBaseConfig(enabled_modes=["keyword", "grep"])
    assert c.default_mode == "keyword"
    assert "hybrid" not in c.enabled_modes


def test_memory_config_defaults_no_llm() -> None:
    c = MemoryStoreConfig()
    assert c.retrieval_modes == ["grep", "keyword"]
    assert c.max_fact_chars == 8192
    assert c.vector_enabled is False
    assert not hasattr(c, "llm_provider")


def test_memory_vector_enabled_by_mode_only() -> None:
    # Embedding is GLOBAL now: listing the mode enables vector.
    assert MemoryStoreConfig(retrieval_modes=["keyword", "vector"]).vector_enabled is True


def test_memory_enabling_vector_auto_enables_hybrid_and_defaults_to_it() -> None:
    # Mirrors the KB face: a vector-enabled memory store fuses (RRF) by default.
    c = MemoryStoreConfig(retrieval_modes=["grep", "keyword", "vector"])
    assert "hybrid" in c.retrieval_modes
    assert c.default_mode == "hybrid"


def test_memory_explicit_default_mode_overrides_hybrid_auto_default() -> None:
    c = MemoryStoreConfig(retrieval_modes=["keyword", "vector"], default_mode="keyword")
    assert c.default_mode == "keyword"
    assert "hybrid" in c.retrieval_modes


def test_memory_legacy_embedding_fields_accepted_but_inert() -> None:
    # The legacy flat ``embedding_*`` fields still parse (CLI/HTTP keep them on
    # the wire) but no longer drive anything — embedding resolves globally.
    c = MemoryStoreConfig(
        retrieval_modes=["keyword", "vector"],
        embedding_provider="local",
        embedding_model="bge-m3",
        embedding_dimensions=1024,
    )
    assert c.embedding_dimensions == 1024
    assert not hasattr(c, "to_embedding_config")


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


def test_frontmatter_malformed_yaml_degrades_to_empty() -> None:
    """A fenced block whose YAML is invalid (e.g. an unquoted value with a
    stray colon, as written by an out-of-band tool) must NOT raise — it
    degrades to empty frontmatter with the body preserved, so one bad file
    cannot crash a whole store scan."""
    text = (
        "---\n"
        "name: Engineering conventions\n"
        "description: catalogued in `agents/` (10 topic files: storage, testing)\n"
        "---\n"
        "the real body\n"
    )
    fm, body = split_frontmatter(text)
    assert fm == {}
    assert body.strip() == "the real body"
