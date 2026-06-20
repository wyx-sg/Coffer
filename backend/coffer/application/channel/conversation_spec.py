"""Resolve a channel peer's sticky choices + channel defaults into the
(agent_key, agent_config) a new conversation is created with.

Structural dimension only: the agent is fixed when a conversation is created
(a conversation cannot be re-keyed), so switching it opens a fresh
conversation built from this spec. The model is parametric (re-read each
turn) and is not handled here.

Pure functions — no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
) -> ConversationSpec:
    """Combine the peer's sticky agent preference with the channel default.

    An empty resulting config is normalized to ``None`` (matching the
    historical pass-through of an absent ``default_agent_config``).
    """
    agent_key = preferred_agent or default_agent
    config: dict[str, Any] = dict(default_agent_config) if default_agent_config else {}
    return ConversationSpec(agent_key=agent_key, agent_config=config or None)
