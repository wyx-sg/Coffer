"""Unit tests for AgentProviderRegistry — the chat platform's agent seam."""

from __future__ import annotations

import pytest

from coffer.application.chat.registry import AgentProviderRegistry
from coffer.domain.errors import UnknownAgent

from .conftest import FakeAgentProvider


def test_register_and_get_returns_provider() -> None:
    registry = AgentProviderRegistry()
    provider = FakeAgentProvider(adapter=None, agent_key="builtin")
    registry.register(provider, display_name="Coffer Assistant")
    assert registry.get("builtin") is provider


def test_get_unknown_agent_raises() -> None:
    registry = AgentProviderRegistry()
    with pytest.raises(UnknownAgent):
        registry.get("does-not-exist")


def test_entries_returns_registered_agents_in_registration_order() -> None:
    registry = AgentProviderRegistry()
    p1 = FakeAgentProvider(adapter=None, agent_key="builtin")
    p2 = FakeAgentProvider(adapter=None, agent_key="second")
    registry.register(p1, display_name="Coffer Assistant")
    registry.register(p2, display_name="Second Agent")

    entries = registry.entries()
    assert [e.provider.agent_key for e in entries] == ["builtin", "second"]
    assert [e.display_name for e in entries] == ["Coffer Assistant", "Second Agent"]


def test_register_same_key_replaces_previous() -> None:
    registry = AgentProviderRegistry()
    first = FakeAgentProvider(adapter=None, agent_key="builtin")
    second = FakeAgentProvider(adapter=None, agent_key="builtin")
    registry.register(first, display_name="First")
    registry.register(second, display_name="Second")
    assert registry.get("builtin") is second
