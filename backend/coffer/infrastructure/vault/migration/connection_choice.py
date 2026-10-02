"""Moving "which connection an agent runs on" from the connection to the agent.

Before this build a provider connection carried ``is_active`` — one boolean for
every agent type it reached. The agent's own record now names the connection it
runs on (``AgentConfig.connection_uid``; spec agent-registry "Carry the
connection an agent runs on on the agent record"), so the upgrade converts each
connection that was active into that field on the agents it reached, and drops
the flag. An agent no connection was chosen for loses its model binding (a
model of a connection it does not run on). It also strips ``wire_api`` from the
agents' records: the field is gone, and ``AgentConfig`` refuses keys it does not
declare.

"Reached" is what the old projection meant: the connection was switched on, was
not a keyless ``ollama`` connection, and its scope named the agent (no scope =
every agent). Where two active connections reached one agent, the first by name
wins — the rule the old build used to project such a state.

This is the one place that knows ``is_active`` ever existed; nothing at runtime
reads it.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from coffer.domain.scope import is_active as scope_reaches

if TYPE_CHECKING:
    from coffer.infrastructure.vault.migration.legacy_db import OldResource

_PROVIDER = "provider"
_AGENT = "agent"
_OLLAMA = "ollama"
_BINDING_KEYS = ("model", "effort", "tier_models")


def settle_connection_choice(resources: list[OldResource]) -> list[OldResource]:
    """``resources`` with every connection's ``is_active`` turned into
    ``connection_uid`` on the agents it reached, and ``wire_api`` removed from
    the agents."""
    agents = [r for r in resources if r.kind == _AGENT]
    chosen: dict[str, str] = {}
    for conn in sorted((r for r in resources if r.kind == _PROVIDER), key=lambda r: r.name):
        if not conn.config.get("is_active") or not conn.enabled:
            continue
        if conn.config.get("protocol") == _OLLAMA:
            continue
        for agent in agents:
            if scope_reaches(conn.scope, agent.uid):
                chosen.setdefault(agent.uid, conn.uid)

    out: list[OldResource] = []
    for r in resources:
        config: dict[str, Any] = dict(r.config)
        if r.kind == _PROVIDER:
            config.pop("is_active", None)
        elif r.kind == _AGENT:
            config.pop("wire_api", None)
            if r.uid in chosen:
                config["connection_uid"] = chosen[r.uid]
            else:
                # The model binding names a model of the connection the agent
                # runs on. With none chosen the agent is on its own login, which
                # nothing reads a binding for; keeping the old provider's model
                # would only show up as a model the agent never uses.
                for key in _BINDING_KEYS:
                    config.pop(key, None)
        out.append(dataclasses.replace(r, config=config))
    return out


__all__ = ["settle_connection_choice"]
