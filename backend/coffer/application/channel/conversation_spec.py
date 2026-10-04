"""Resolve a channel peer's sticky choices + channel defaults into the
(agent_key, agent_config) a new conversation is created with.

The agent and the working directory are structural: fixed when a conversation
is created (a conversation cannot be re-keyed, and an agent session is tied to
its directory), so switching either opens a fresh conversation built from this
spec. The model stays parametric — ``/model`` re-points the SAME
conversation — and is also remembered on the thread, so a fresh conversation
opens on it too.

Pure functions — no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from coffer.domain.scope import Scope, is_active


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
    preferred_model: str | None = None,
    preferred_cwd: str | None = None,
) -> ConversationSpec:
    """Combine the peer's sticky agent preference with the channel defaults.

    ``agent_scope`` is the channel's scope (ADR per-agent-resource-scope): it
    names the agents the channel may drive. A sticky preference outside it is
    dropped in favour of the channel default, so narrowing a channel's scope
    takes effect on the very next conversation instead of waiting for whoever
    set that preference to change it back. An unrestricted scope keeps every
    preference, which is what every channel did before scope existed.

    An empty resulting config is normalized to ``None`` (matching the
    historical pass-through of an absent ``default_agent_config``).
    """
    if preferred_agent and is_active(agent_scope, preferred_agent):
        agent_key = preferred_agent
    else:
        agent_key = default_agent
    config: dict[str, Any] = dict(default_agent_config) if default_agent_config else {}
    # The thread's sticky settings (spec channels "Keep a chat's agent, model and
    # directory across its conversations") override the channel's defaults. A model
    # chosen for one agent means nothing to another, so it rides only while the
    # sticky agent is the one in effect; the directory is the agent's workplace
    # and rides regardless.
    if agent_key == preferred_agent and preferred_model:
        config["model"] = preferred_model
    if preferred_cwd:
        config["cwd"] = preferred_cwd
    return ConversationSpec(agent_key=agent_key, agent_config=config or None)
