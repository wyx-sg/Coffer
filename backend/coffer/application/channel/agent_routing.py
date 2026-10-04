"""Which agents a channel may drive, in one place (ADR per-agent-resource-scope).

A channel's framework-level ``scope`` names the agents it may route turns to —
the inbound mirror of every other kind's "delivered to these agents". Three
surfaces ask that question and they must agree, because a disagreement is
visible to the user as a list that offers an agent the validator then rejects:

- ``/new <agent>`` with a name no routable agent answers to lists the ones
  that do;
- ``/new <agent>`` validates the name typed against the same set;
- every turn resolves the agent it runs as.

Pure functions over an already-bound channel: the scope travels on
``ChannelBinding``, refreshed by the runtime's reconcile loop, so nothing here
does I/O.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.domain.scope import is_active

if TYPE_CHECKING:
    from coffer.application.channel.ports import AgentCatalogPort, ChannelBinding


def routable_choices(binding: ChannelBinding, agents: AgentCatalogPort) -> list[tuple[str, str]]:
    """``(key, display name)`` for the agents this channel may route to."""
    return [
        (key, name) for key, name in agents.agent_choices() if is_active(binding.agent_scope, key)
    ]


def effective_agent(binding: ChannelBinding, preferred: str | None) -> str:
    """The agent a turn in this thread actually runs as.

    The thread's sticky ``/new <agent>`` choice wins, but only while the channel may
    still drive it: narrowing a channel's scope after someone switched would
    otherwise leave that thread routing to an agent the channel is no longer
    allowed to reach. The fallback is the channel default, which the kind's own
    validation keeps inside the scope.
    """
    if preferred and is_active(binding.agent_scope, preferred):
        return preferred
    return binding.default_agent
