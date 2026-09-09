"""Unit tests for the substrate configs, embedding config, and frontmatter."""

import pytest
from pydantic import ValidationError

from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.infrastructure.knowledge.frontmatter import (
    body_of,
    render_frontmatter,
    split_frontmatter,
)


def test_config_defaults() -> None:
    c = KnowledgeConfig()
    assert c.retrieval_modes == ["grep", "keyword"]
    assert c.default_mode == "keyword"
    assert c.max_entry_chars == 8192
    assert c.vector_enabled is False
    assert not hasattr(c, "llm_provider")


def test_vector_enabled_by_mode_only() -> None:
    # Embedding is installation-wide: listing the mode enables vector, and no
    # per-scope embedding config exists to configure.
    assert KnowledgeConfig(retrieval_modes=["keyword", "vector"]).vector_enabled is True


def test_embedding_fields_are_gone() -> None:
    """The merged config carries no embedding fields — both faces' were dead."""
    for field in (
        "embedding",
        "embedding_provider",
        "embedding_model",
        "embedding_base_url",
        "embedding_credential_ref",
        "embedding_dimensions",
    ):
        assert field not in KnowledgeConfig.model_fields


def test_overlap_bound() -> None:
    with pytest.raises(ValidationError, match="chunk_overlap"):
        KnowledgeConfig(chunk_size=100, chunk_overlap=80)


def test_default_mode_must_be_enabled() -> None:
    with pytest.raises(ValidationError, match="default_mode"):
        KnowledgeConfig(retrieval_modes=["grep"], default_mode="keyword")


def test_enabling_vector_auto_enables_hybrid_and_defaults_to_it() -> None:
    # Enabling vector adds hybrid to the set automatically and makes hybrid the
    # default: a vector-enabled scope gets RRF fusion by default.
    c = KnowledgeConfig(retrieval_modes=["keyword", "grep", "vector"])
    assert "hybrid" in c.retrieval_modes
    assert c.default_mode == "hybrid"
    assert c.vector_enabled is True


def test_explicit_default_mode_overrides_hybrid_auto_default() -> None:
    # A caller who explicitly sets default_mode keeps it (no silent override).
    c = KnowledgeConfig(retrieval_modes=["keyword", "grep", "vector"], default_mode="keyword")
    assert c.default_mode == "keyword"
    assert "hybrid" in c.retrieval_modes


def test_keyword_stays_default_when_vector_off() -> None:
    c = KnowledgeConfig(retrieval_modes=["keyword", "grep"])
    assert c.default_mode == "keyword"
    assert "hybrid" not in c.retrieval_modes


def test_merged_identities_default_empty() -> None:
    assert KnowledgeConfig().merged_identities == []


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
