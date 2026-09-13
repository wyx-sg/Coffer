"""Which agents a channel may drive, in one place (ADR per-agent-resource-scope).

A channel's framework-level ``scope`` names the agents it may route turns to —
the inbound mirror of every other kind's "delivered to these agents". Three
surfaces ask that question and they must agree, because a disagreement is
visible to the user as a card that offers an agent the validator then rejects:

- ``/agent`` with no argument lists the agents, and renders them as a card;
- ``/agent <key>`` and a card tap validate the chosen key;
- every turn resolves the agent it runs as.

Pure functions over an already-bound channel: the scope travels on
``ChannelBinding``, refreshed by the runtime's reconcile loop, so nothing here
does I/O.

Only the scope's AGENT axis is read. The machine axis is the runtime's gate,
answered once before the adapter starts — a bound channel is by definition one
this machine was allowed to run — so re-asking it here could only ever return
the same yes, at the cost of every routing seam needing this machine's id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.domain.scope import agent_axis_admits

if TYPE_CHECKING:
    from coffer.application.channel.ports import AgentCatalogPort, ChannelBinding


def routable_keys(binding: ChannelBinding, agents: AgentCatalogPort) -> list[str]:
    """The registered agent keys this channel may route to, in registry order."""
    return [key for key in agents.agent_keys() if agent_axis_admits(binding.agent_scope, key)]


def routable_choices(binding: ChannelBinding, agents: AgentCatalogPort) -> list[tuple[str, str]]:
    """``(key, display name)`` for the agents this channel may route to."""
    return [
        (key, name)
        for key, name in agents.agent_choices()
        if agent_axis_admits(binding.agent_scope, key)
    ]


def effective_agent(binding: ChannelBinding, preferred: str | None) -> str:
    """The agent a turn in this thread actually runs as.

    The thread's sticky ``/agent`` choice wins, but only while the channel may
    still drive it: narrowing a channel's scope after someone switched would
    otherwise leave that thread routing to an agent the channel is no longer
    allowed to reach. The fallback is the channel default, which the kind's own
    validation keeps inside the scope.
    """
    if preferred and agent_axis_admits(binding.agent_scope, preferred):
        return preferred
    return binding.default_agent
