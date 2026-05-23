"""Unit tests for MemoryStoreConfig validation. Pure — no I/O."""

import pytest

from coffer.domain.memory.config import MemoryStoreConfig


def test_default_provider_none() -> None:
    c = MemoryStoreConfig()
    assert c.llm_provider == "none"
    assert c.max_memory_chars == 8192
    assert c.effective_endpoint is None


def test_ollama_requires_model() -> None:
    with pytest.raises(ValueError, match="llm_model"):
        MemoryStoreConfig(llm_provider="ollama")


def test_ollama_default_endpoint() -> None:
    c = MemoryStoreConfig(llm_provider="ollama", llm_model="llama3.1")
    assert c.effective_endpoint == "http://localhost:11434"


def test_openai_requires_credential_ref() -> None:
    with pytest.raises(ValueError, match="llm_credential_ref"):
        MemoryStoreConfig(llm_provider="openai", llm_model="gpt-4o-mini")


def test_openai_complete() -> None:
    c = MemoryStoreConfig(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_credential_ref="openai-key",
    )
    assert c.llm_provider == "openai"
    assert c.llm_credential_ref == "openai-key"
