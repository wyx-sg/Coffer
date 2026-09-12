"""Unit tests for the global embedding config value objects.

The config NAMES a connection instead of restating one, so the domain's whole
job here is: is vector active, which embedding client does the named
connection's wire imply, and what does the projected ``EmbeddingConfig`` carry.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.embedding_config import (
    EmbeddingEndpoint,
    GlobalEmbeddingConfig,
    embedding_provider_for,
)


def _cfg(
    *,
    enabled: bool = True,
    connection: str | None = "acme",
    model: str | None = "text-embedding-3-large",
    dimensions: int = 3072,
) -> GlobalEmbeddingConfig:
    return GlobalEmbeddingConfig(
        enabled=enabled,
        connection=connection,
        model=model,
        dimensions=dimensions,
        default_chunk_size=512,
        default_chunk_overlap=64,
        updated_at=datetime(2026, 9, 12, tzinfo=UTC),
    )


def _endpoint(
    protocol: str = "openai",
    *,
    base_url: str = "https://api.openai.com/v1",
    credential_ref: str | None = "provider/acme/key",
) -> EmbeddingEndpoint:
    return EmbeddingEndpoint(
        protocol=protocol,
        base_url=base_url,
        credential_ref=credential_ref,
        offered_models=("text-embedding-3-large",),
    )


# --- embedding_provider_for ---------------------------------------------------


@pytest.mark.parametrize(
    ("protocol", "expected"),
    [
        ("openai", "openai"),
        # An endpoint whose probe was inconclusive is in practice
        # OpenAI-compatible, so it gets the same client.
        ("unknown", "openai"),
        ("ollama", "ollama"),
    ],
)
def test_a_wire_that_serves_embeddings_names_its_client(protocol: str, expected: str) -> None:
    assert embedding_provider_for(protocol) == expected


@pytest.mark.parametrize("protocol", ["anthropic", "", "OPENAI", "grpc"])
def test_a_wire_with_no_embeddings_api_has_no_client(protocol: str) -> None:
    """``anthropic`` is absent on purpose — that wire exposes no embeddings API,
    so naming such a connection is refused rather than half-configured."""
    assert embedding_provider_for(protocol) is None


# --- is_active ----------------------------------------------------------------


def test_is_active_needs_the_switch_and_both_names() -> None:
    assert _cfg().is_active() is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"enabled": False},
        {"connection": None},
        {"model": None},
        {"connection": ""},
        {"model": ""},
    ],
)
def test_is_active_is_false_without_the_switch_or_a_name(kwargs: dict[str, object]) -> None:
    assert _cfg(**kwargs).is_active() is False  # type: ignore[arg-type]


# --- to_embedding_config ------------------------------------------------------


def test_to_embedding_config_carries_the_connections_endpoint() -> None:
    projected = _cfg(dimensions=1024).to_embedding_config(_endpoint())

    assert projected is not None
    assert projected.provider == "openai"
    assert projected.model == "text-embedding-3-large"
    assert projected.base_url == "https://api.openai.com/v1"
    assert projected.credential_ref == "provider/acme/key"
    # Width is the CONFIG's: the connection says where, the config says how wide.
    assert projected.dimensions == 1024


def test_to_embedding_config_carries_a_keyless_ollama_endpoint() -> None:
    projected = _cfg().to_embedding_config(
        _endpoint("ollama", base_url="http://127.0.0.1:11434", credential_ref=None)
    )

    assert projected is not None
    assert projected.provider == "ollama"
    assert projected.credential_ref is None


def test_to_embedding_config_is_none_when_the_config_is_inactive() -> None:
    assert _cfg(enabled=False).to_embedding_config(_endpoint()) is None
    assert _cfg(connection=None).to_embedding_config(_endpoint()) is None
    assert _cfg(model=None).to_embedding_config(_endpoint()) is None


def test_to_embedding_config_is_none_when_the_connection_is_gone() -> None:
    """A deleted connection degrades retrieval to keyword — the same state an
    install that never configured embedding is already in."""
    assert _cfg().to_embedding_config(None) is None


def test_to_embedding_config_is_none_when_the_wire_serves_no_embeddings() -> None:
    assert _cfg().to_embedding_config(_endpoint("anthropic")) is None
