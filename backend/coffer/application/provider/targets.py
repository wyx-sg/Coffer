"""Which agents a connection reaches, and which connection an agent is on
(ADR per-agent-resource-scope; spec provider-switching).

Two different questions live here and must not be confused:

- **Reach** — which agents a connection MAY serve. It is the resource's
  framework-level ``scope``, narrowed by its ``enabled`` switch, and this module
  is the single seam where the agent UIDS a scope holds are resolved into
  ``AgentType`` (ADR identity-is-the-uid-inside-the-file): a uid says nothing
  about the agent's type by itself, only the registry knows, which is why
  ``scoped_targets`` takes the agent rows.
- **Choice** — which connection one agent actually runs on. That is a field of
  the agent record (``AgentConfig.connection_uid``), so it can name at most one
  connection by construction, and :func:`connection_for_agent` is the ONE
  function that answers it. The projection reconcile target, the model proxy's
  state, the chat model catalogue, the usage meter and the switch operations all
  ask it, so no two of them can ever pick different connections for one agent.

Reach has two readings, and collapsing them loses information:

- **Configured reach** (``scoped_targets``) — which agents this connection is
  set up to cover, whether or not it is switched on right now. This is what a
  management surface should show: blanking a connection's agent list because
  the user disabled it makes the list look erased, and re-enabling appear to
  restore data that was never lost.
- **Effective reach** (:func:`reaches`) — one agent, and the user's ``enabled``
  switch applied. What routing and the reconcile paths want.
"""

from __future__ import annotations

from collections.abc import Iterable

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.scope import is_active


def scoped_targets(
    resource: Resource, cfg: ProviderConfig, agents: list[Resource]
) -> list[AgentType]:
    """The agent types ``resource`` is CONFIGURED to cover, in ``AgentType`` order.

    ``agents`` is the agent registry — every ``agent`` resource row, not only
    the enabled ones. Whether an agent is switched off is the projector's
    business at write time; leaving a disabled agent's type out of the reach
    here would hide it from the management surface and, worse, from
    ``activate``'s ``skipped`` list, which exists to tell the user that a type
    they scoped the connection to received nothing.

    A uid in the scope that matches no registered agent contributes no type —
    the scope layer's own rule for a reference to an agent this machine does
    not have. It is dropped rather than guessed at, which narrows the reach and
    never widens it.

    A keyless (ollama) connection returns nothing whatever its scope says: it
    is Coffer's internal engine's endpoint and there is no key to write into an
    agent's config, so it covers no agent even in principle. That used to be a
    config-level validation rule; it is enforced here instead, because scope
    lives outside the config and the rule is about projection, not about the
    config's shape.

    ``enabled`` is not consulted — see this module's docstring for why the
    configured reach and the effective projection are kept apart.
    """
    if cfg.protocol is Protocol.OLLAMA:
        return []
    if resource.scope is None or resource.scope.agents is None:
        # Unscoped: every agent type, including one whose agent is not
        # registered on this machine yet. Answering from the registry instead
        # would make "every agent" mean "every agent I happen to have", and a
        # connection created before the user installed Codex would quietly
        # never reach it.
        return list(AgentType)
    reached: set[AgentType] = set()
    for agent in agents:
        if not is_active(resource.scope, agent.uid):
            continue
        try:
            reached.add(AgentConfig.model_validate(agent.config).type)
        except Exception:
            # A row whose config no longer parses is surfaced by the agent
            # routes; here it simply contributes no type. Skipping narrows the
            # reach, which is the safe direction — the projector could not
            # write that agent's file anyway.
            continue
    return [t for t in AgentType if t in reached]


def reaches(resource: Resource, cfg: ProviderConfig, agent: Resource) -> bool:
    """Whether ``resource`` may serve ``agent`` right now: switched on, not a
    keyless (ollama) connection, and its scope names the agent (an unscoped
    connection names every agent). The agent's own ``enabled`` switch is its
    caller's concern."""
    if not resource.enabled or cfg.protocol is Protocol.OLLAMA:
        return False
    return is_active(resource.scope, agent.uid)


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


__all__ = ["connection_for_agent", "reaches", "scoped_targets"]
