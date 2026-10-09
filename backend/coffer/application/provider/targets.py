"""Which agents a connection reaches, and which connection an agent is on
(ADR provider-reach-is-what-its-addresses-serve; spec provider-switching).

Two different questions live here and must not be confused:

- **Reach** — which agents a connection MAY serve. It is what the connection's
  addresses serve (Claude Code needs an Anthropic one, Codex an OpenAI one),
  narrowed by its ``enabled`` switch. A connection has no per-agent scope: a
  scope stored before that rule is ignored.
- **Choice** — which connection one agent actually runs on. That is a field of
  the agent record (``AgentConfig.connection_uid``), so it can name at most one
  connection by construction, and :func:`connection_for_agent` is the ONE
  function that answers it. The projection reconcile target, the model proxy's
  state, the chat model catalogue, the usage meter and the switch operations all
  ask it, so no two of them can ever pick different connections for one agent.

Reach has two readings, and collapsing them loses information:

- **Configured reach** (``scoped_targets``) — which agents this connection can
  cover, whether or not it is switched on right now. This is what a
  management surface should show: blanking a connection's agent list because
  the user disabled it makes the list look erased.
- **Effective reach** (:func:`reaches`) — one agent, and the user's ``enabled``
  switch applied. What routing and the reconcile paths want.
"""

from __future__ import annotations

from collections.abc import Iterable

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.agent_projection import PROVIDER_PROJECTIONS
from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.resource import Resource

#: The wire each agent type speaks to a provider, as its projection declares it.
_AGENT_WIRE = {p.agent_type: p.protocols[0] for p in PROVIDER_PROJECTIONS if p.protocols}


def agent_wire(agent_type: AgentType) -> str | None:
    """The wire ``agent_type`` speaks to a provider (``anthropic`` / ``openai``)."""
    return _AGENT_WIRE.get(agent_type)


def serves(cfg: ProviderConfig, agent_type: AgentType) -> bool:
    """Whether ``cfg`` has an address for the wire ``agent_type`` speaks (ADR
    one-connection-serves-both-wires): Claude Code needs an Anthropic one,
    Codex an OpenAI one."""
    wire = _AGENT_WIRE.get(agent_type)
    return wire is not None and wire in cfg.served_wires()


def served_agents(cfg: ProviderConfig) -> list[AgentType]:
    """The agent types ``cfg`` can serve, in ``AgentType`` order."""
    return [t for t in AgentType if serves(cfg, t)]


def scoped_targets(
    resource: Resource, cfg: ProviderConfig, agents: list[Resource]
) -> list[AgentType]:
    """The agent types ``resource`` covers, in ``AgentType`` order: the ones its
    addresses serve (ADR provider-reach-is-what-its-addresses-serve).

    A connection has no per-agent scope: which connection an agent runs on is
    the agent's own choice, and the agents a connection can serve follow from
    its addresses. A scope stored before that rule is ignored, so it can
    neither narrow nor widen the answer. ``agents`` is kept for the callers'
    shape and not read.

    ``enabled`` is not consulted — see this module's docstring for why the
    configured reach and the effective projection are kept apart.
    """
    del agents
    if cfg.protocol is Protocol.OLLAMA:
        return []
    return served_agents(cfg)


def reaches(resource: Resource, cfg: ProviderConfig, agent: Resource) -> bool:
    """Whether ``resource`` may serve ``agent`` right now: switched on and
    with an address for the wire the agent speaks."""
    if not resource.enabled or cfg.protocol is Protocol.OLLAMA:
        return False
    try:
        agent_type = AgentConfig.model_validate(agent.config).type
    except ValueError:
        return False
    return serves(cfg, agent_type)


def connection_for_agent(
    agent: Resource, connections: Iterable[Resource]
) -> tuple[Resource, ProviderConfig] | None:
    """The connection ``agent`` runs on, or ``None`` for its own built-in login.

    Reads the agent's ``connection_uid`` and checks that the connection it names
    still exists, parses, and :func:`reaches` the agent. A pointer that fails any
    of those — a connection since deleted, switched off, re-scoped away from the
    agent, or turned into an ollama one — is NOT followed: the agent is on its own
    login as far as Coffer's routing is concerned, and the reconcile target
    reports what that leaves behind in the agent's file rather than silently
    re-routing it elsewhere. There is no tie-break to apply: the choice is one
    field of one record.
    """
    try:
        uid = AgentConfig.model_validate(agent.config).connection_uid
    except ValueError:
        return None  # a row whose config no longer parses is surfaced by the agent routes
    if uid is None:
        return None
    for resource in connections:
        if resource.uid != uid:
            continue
        try:
            cfg = ProviderConfig.model_validate(resource.config)
        except ValueError:
            return None
        return (resource, cfg) if reaches(resource, cfg, agent) else None
    return None


__all__ = [
    "agent_wire",
    "connection_for_agent",
    "reaches",
    "scoped_targets",
    "served_agents",
    "serves",
]
