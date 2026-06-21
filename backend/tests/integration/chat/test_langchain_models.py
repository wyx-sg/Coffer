"""Integration tests for build_chat_model — the real LangChain provider seam.

These construct real LangChain client objects (no network calls) to cover the
per-wire builders and their credential/base_url handling, which the scripted
LangGraph tests never exercise. ``build_chat_model`` now consumes a provider
connection (``ProviderConfig``) dispatched by ``wire_format``.
"""

from __future__ import annotations

import pytest

from coffer.domain.provider.config import ProviderConfig, WireFormat
from coffer.infrastructure.chat.langchain_models import build_chat_model


def _conn(wire: WireFormat, **overrides) -> ProviderConfig:  # type: ignore[no-untyped-def]
    base = {
        "wire_format": wire,
        "base_url": "http://localhost:11434" if wire is WireFormat.OLLAMA else "https://api.test",
        "credential_ref": None if wire is WireFormat.OLLAMA else "ref",
        "model": "test-model",
    }
    base.update(overrides)
    return ProviderConfig(**base)  # type: ignore[arg-type]


def test_anthropic_resolves_credential_and_builds_client() -> None:
    calls: list[str] = []

    def resolver(ref: str) -> str:
        calls.append(ref)
        return "secret-key"

    model = build_chat_model(_conn(WireFormat.ANTHROPIC), resolver)

    assert calls == ["ref"]  # the credential ref was resolved
    assert model.__class__.__name__ == "ChatAnthropic"


def test_openai_resolves_credential_and_builds_client() -> None:
    calls: list[str] = []
    model = build_chat_model(
        _conn(WireFormat.OPENAI), lambda ref: calls.append(ref) or "secret-key"
    )
    assert calls == ["ref"]
    assert model.__class__.__name__ == "ChatOpenAI"


def test_openai_passes_base_url_for_compatible_endpoint() -> None:
    # An OpenAI-COMPATIBLE endpoint (aggregator/Azure/OpenRouter) must reach
    # config.base_url, not silently fall back to api.openai.com.
    model = build_chat_model(
        _conn(WireFormat.OPENAI, base_url="https://apihub.example.com/v1"),
        lambda ref: "secret-key",
    )
    assert "apihub.example.com/v1" in str(model.openai_api_base)


def test_ollama_uses_base_url_and_skips_credential() -> None:
    def resolver(ref: str) -> str:  # pragma: no cover - must not be called
        raise AssertionError("ollama must not resolve a credential")

    model = build_chat_model(_conn(WireFormat.OLLAMA), resolver)

    assert model.__class__.__name__ == "ChatOllama"


def test_resolver_failure_propagates() -> None:
    def resolver(ref: str) -> str:
        raise RuntimeError("keychain locked")

    with pytest.raises(RuntimeError, match="keychain locked"):
        build_chat_model(_conn(WireFormat.ANTHROPIC), resolver)
