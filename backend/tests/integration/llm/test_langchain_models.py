"""Integration tests for build_chat_model — the real LangChain provider seam.

These construct real LangChain client objects (no network calls) to cover the
per-wire builders and their secret/base_url handling, which the scripted
LangGraph tests never exercise. ``build_chat_model`` now consumes a provider
connection (``ProviderConfig``) dispatched by ``wire_format``.
"""

from __future__ import annotations

import pytest

from coffer.domain.provider.config import Protocol, ProviderConfig, ResolvedConnection
from coffer.infrastructure.llm.langchain_models import build_chat_model


def _conn(wire: Protocol, **overrides) -> ResolvedConnection:  # type: ignore[no-untyped-def]
    base = {
        "protocol": wire,
        "base_url": "http://localhost:11434" if wire is Protocol.OLLAMA else "https://api.test",
        "secret_ref": None if wire is Protocol.OLLAMA else "ref",
    }
    base.update(overrides)
    return ResolvedConnection(config=ProviderConfig(**base), model="test-model")  # type: ignore[arg-type]


def test_anthropic_resolves_secret_and_builds_client() -> None:
    calls: list[str] = []

    def resolver(ref: str) -> str:
        calls.append(ref)
        return "secret-key"

    model = build_chat_model(_conn(Protocol.ANTHROPIC), resolver)

    assert calls == ["ref"]  # the secret ref was resolved
    assert model.__class__.__name__ == "ChatAnthropic"


def test_openai_resolves_secret_and_builds_client() -> None:
    calls: list[str] = []
    model = build_chat_model(_conn(Protocol.OPENAI), lambda ref: calls.append(ref) or "secret-key")
    assert calls == ["ref"]
    assert model.__class__.__name__ == "ChatOpenAI"


def test_openai_passes_base_url_for_compatible_endpoint() -> None:
    # An OpenAI-COMPATIBLE endpoint (aggregator/Azure/OpenRouter) must reach
    # config.base_url, not silently fall back to api.openai.com.
    model = build_chat_model(
        _conn(Protocol.OPENAI, base_url="https://apihub.example.com/v1"),
        lambda ref: "secret-key",
    )
    assert "apihub.example.com/v1" in str(model.openai_api_base)


def test_ollama_uses_base_url_and_skips_secret() -> None:
    def resolver(ref: str) -> str:  # pragma: no cover - must not be called
        raise AssertionError("ollama must not resolve a secret")

    model = build_chat_model(_conn(Protocol.OLLAMA), resolver)

    assert model.__class__.__name__ == "ChatOllama"


def test_resolver_failure_propagates() -> None:
    def resolver(ref: str) -> str:
        raise RuntimeError("keychain locked")

    with pytest.raises(RuntimeError, match="keychain locked"):
        build_chat_model(_conn(Protocol.ANTHROPIC), resolver)


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="build the engine's chat model for an unclassified or keyless local connection",
)
def test_unknown_protocol_builds_an_openai_compatible_client() -> None:
    model = build_chat_model(_conn(Protocol.UNKNOWN), lambda ref: "secret-key")
    assert model.__class__.__name__ == "ChatOpenAI"


def test_keyless_local_runtime_builds_with_a_placeholder_key() -> None:
    from coffer.domain.provider.config import LocalRuntime

    def resolver(ref: str) -> str:  # pragma: no cover - must not be called
        raise AssertionError("a keyless connection resolves no secret")

    model = build_chat_model(
        _conn(
            Protocol.ANTHROPIC,
            base_url="http://127.0.0.1:11434",
            secret_ref=None,
            local_runtime=LocalRuntime(runtime="ollama"),
        ),
        resolver,
    )
    assert model.__class__.__name__ == "ChatAnthropic"
