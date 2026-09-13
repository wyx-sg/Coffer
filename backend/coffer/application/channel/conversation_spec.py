"""Resolve a channel peer's sticky choices + channel defaults into the
(agent_key, agent_config) a new conversation is created with.

Structural dimension only for the agent: it is fixed when a conversation is
created (a conversation cannot be re-keyed), so switching it opens a fresh
conversation built from this spec. The model stays parametric — ``/model``
re-points the SAME conversation — and a fresh conversation simply starts on the
bound agent's own CLI default, because a channel curates no models.

Pure functions — no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from coffer.domain.scope import Scope, agent_axis_admits


@dataclass(frozen=True)
class ConversationSpec:
    """The inputs to ``create_conversation`` for a channel-driven conversation."""

    agent_key: str
    agent_config: dict[str, Any] | None


def resolve_conversation_spec(
    *,
    default_agent: str,
    default_agent_config: dict[str, Any] | None,
    preferred_agent: str | None,
    agent_scope: Scope | None = None,
) -> ConversationSpec:
    """Combine the peer's sticky agent preference with the channel defaults.

    ``agent_scope`` is the channel's scope (ADR per-agent-resource-scope); its
    AGENT axis names the agents it may drive. A sticky preference outside that
    axis is dropped in favour of the channel default, so narrowing a channel's
    scope takes effect on the very next conversation instead of waiting for
    whoever set that preference to change it back. An unrestricted axis keeps
    every preference, which is what every channel did before scope existed. The
    machine axis says nothing about agents and is not read here — the runtime
    settled it before this channel was ever bound.

    An empty resulting config is normalized to ``None`` (matching the
    historical pass-through of an absent ``default_agent_config``).
    """
    if preferred_agent and agent_axis_admits(agent_scope, preferred_agent):
        agent_key = preferred_agent
    else:
        agent_key = default_agent
    config: dict[str, Any] = dict(default_agent_config) if default_agent_config else {}
    return ConversationSpec(agent_key=agent_key, agent_config=config or None)
