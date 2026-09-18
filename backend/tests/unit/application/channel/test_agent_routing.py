"""Which agents a channel may drive (ADR per-agent-resource-scope).

Pure narrowing, asserted here so the three surfaces that ask the question —
the `/agent` listing, the `/agent` card, and the validation of a chosen key —
provably read one answer. The end-to-end behaviour lives in
``tests/integration/channel/test_agent_scope.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from coffer.application.channel.agent_routing import (
    effective_agent,
    routable_choices,
    routable_keys,
)
from coffer.application.channel.ports import ChannelBinding
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope


class _Catalog:
    """An ``AgentCatalogPort`` with two agents registered."""

    def agent_keys(self) -> list[str]:
        return ["claude_code", "codex"]

    def agent_choices(self) -> list[tuple[str, str]]:
        return [("claude_code", "Claude Code"), ("codex", "Codex")]


def _channel_row() -> Resource:
    now = datetime(2026, 9, 13, tzinfo=UTC)
    return Resource(
        id=1,
        uid="uid-of-the-channel",
        kind="channel",
        name="tg",
        description=None,
        config={"channel_type": "telegram"},
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def _binding(scope: Scope | None, default_agent: str = "claude_code") -> ChannelBinding:
    adapter: Any = object()
    # Everything on a binding below the gate is in agent KEYS — the scope
    # included, because the gate projected it there (``wanted.Routing``). The
    # channel's own row carries uids and nothing here reads them.
    return ChannelBinding(
        resource=_channel_row(),
        channel_type="telegram",
        default_agent=default_agent,
        default_agent_config=None,
        adapter=adapter,
        agent_scope=scope,
    )


def test_unscoped_channel_may_drive_every_agent() -> None:
    # The pre-scope default, which is why channels need no data migration.
    b = _binding(None)
    assert routable_keys(b, _Catalog()) == ["claude_code", "codex"]
    assert routable_choices(b, _Catalog()) == [
        ("claude_code", "Claude Code"),
        ("codex", "Codex"),
    ]


def test_scope_narrows_keys_and_choices_identically() -> None:
    b = _binding(Scope(agents=["codex"]))
    assert routable_keys(b, _Catalog()) == ["codex"]
    assert routable_choices(b, _Catalog()) == [("codex", "Codex")]


def test_a_dormant_channel_may_drive_nothing() -> None:
    b = _binding(Scope(agents=[]))
    assert routable_keys(b, _Catalog()) == []
    assert routable_choices(b, _Catalog()) == []


def test_an_agent_scoped_in_before_it_exists_simply_never_matches() -> None:
    # Unknown names in a scope are legal by design (ADR per-agent-resource-scope); the
    # narrowing intersects with the registry rather than trusting the list.
    b = _binding(Scope(agents=["codex", "not-installed-yet"]))
    assert routable_keys(b, _Catalog()) == ["codex"]


def test_effective_agent_keeps_an_in_scope_sticky_choice() -> None:
    assert effective_agent(_binding(Scope(agents=["claude_code", "codex"])), "codex") == "codex"


def test_effective_agent_drops_a_sticky_choice_the_scope_excludes() -> None:
    # Narrowing a channel after someone switched must not leave the thread
    # routing to an agent the channel may no longer reach.
    assert effective_agent(_binding(Scope(agents=["claude_code"])), "codex") == "claude_code"


def test_effective_agent_falls_back_when_nothing_is_sticky() -> None:
    assert effective_agent(_binding(None), None) == "claude_code"
