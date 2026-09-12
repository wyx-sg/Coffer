"""Resolve a channel peer's sticky choices + channel defaults into the
(agent_key, agent_config) a new conversation is created with, and the channel's
own model curation rules over it.

Structural dimension only for the agent: it is fixed when a conversation is
created (a conversation cannot be re-keyed), so switching it opens a fresh
conversation built from this spec. The model stays parametric — ``/model``
re-points the SAME conversation — but a fresh conversation still has to START
somewhere, and the channel says where (FR-071).

Pure functions — no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
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
    default_model: str | None = None,
) -> ConversationSpec:
    """Combine the peer's sticky agent preference with the channel defaults.

    ``default_model`` is the channel's own answer to "what does a conversation
    here start on" and therefore outranks any ``model`` left inside the raw
    ``default_agent_config`` blob: the blob is provider passthrough, the field
    is the setting the user edited. ``None`` writes no ``model`` at all, so the
    agent's CLI default applies — the behaviour of an unconfigured channel.

    An empty resulting config is normalized to ``None`` (matching the
    historical pass-through of an absent ``default_agent_config``).
    """
    agent_key = preferred_agent or default_agent
    config: dict[str, Any] = dict(default_agent_config) if default_agent_config else {}
    if default_model:
        config["model"] = default_model
    return ConversationSpec(agent_key=agent_key, agent_config=config or None)


def narrow_to_allowed(picks: Sequence[str], allowed: Sequence[str]) -> list[str]:
    """The models a channel's ``/model`` card may offer.

    ``allowed`` EMPTY means the channel curates nothing and everything the bound
    agent offers stands. Otherwise the channel's order is what the card shows:
    the user arranged that list, and an allowed id the agent no longer reports
    is still offered — the channel, not this build of the CLI, is the authority
    on what this chat may be put on, and a name Coffer does not recognise is
    passed to the CLI verbatim anyway.
    """
    if not allowed:
        return list(picks)
    return list(dict.fromkeys(allowed))


def refuse_model(name: str, allowed: Sequence[str]) -> str | None:
    """The refusal text for ``/model <name>`` outside the channel's range, or
    ``None`` when the switch is allowed (which an empty range always is)."""
    if not allowed or name in allowed:
        return None
    return f"🚫 '{name}' is not available on this channel.\nAllowed models: {', '.join(allowed)}"
