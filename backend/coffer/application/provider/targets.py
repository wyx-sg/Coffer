"""Which agents a connection projects into (ADR per-agent-resource-scope).

Five callers, two questions: the switch (``ProviderService``), the per-agent
key lookup the turn machinery does, the post-import projection reconcile and
the boot self-heal all want the effective projection; the management surface
wants the configured reach. Before scope reached this kind the answer lived in the
config as ``compatible_agents``; it is now the resource's framework-level
``scope``, and this module is the single seam where the agent UIDS it holds are
resolved into ``AgentType`` — keeping the provider's own config module
independent of the agent kind.

**The resolution needs the agent rows**, which is why every function here takes
them. A scope names agents by uid (ADR resource-identity-is-an-immutable-uid)
and a uid says nothing about the agent's type by itself; only the registry
knows which product a uid is. That replaced a comparison of an agent's TYPE
value against the scope list — one of the three private vocabularies the uid
removed, and the one that made a provider scope mean something different from a
skill scope while both were called ``scope.agents``.

Projection stays keyed by TYPE rather than by the individual agent, because the
file a projection writes is the agent PRODUCT's (``~/.claude/settings.json``),
shared by every registered agent of that type, and ``is_active`` is one flag
per type. So a type is in reach when a registered agent of that type is in
scope — the same meaning the old type-valued list had, asked of the registry
instead of assumed.

There are two questions here, not one, and collapsing them loses information:

- **Configured reach** (``scoped_targets``) — which agents this connection is
  set up to cover, whether or not it is switched on right now. This is what a
  management surface should show: blanking a connection's agent list because
  the user disabled it makes the list look erased, and re-enabling appear to
  restore data that was never lost.
- **Effective projection** (``projection_targets``) — which agents it actually
  writes a key for, i.e. the configured reach intersected with the user's
  ``enabled`` switch. This is what the routing and reconcile paths want.

Three inputs feed those, each answering something different:

- ``scope`` — WHICH agents the connection may reach. ``None`` (unscoped) means
  every agent, per the framework, and is what a credentialed connection is
  created with.
- ``enabled`` — the user's switch on the resource itself. It narrows the
  effective projection to nothing, and deliberately does NOT narrow the
  configured reach: ``enabled`` travels on the same payload, so a client that
  wants the intersection can take it, while one that wants to render the
  configured list still can.
- ``is_active`` — NOT a narrowing at all, and deliberately not read by either.
  It records whether this is the connection currently *projected* into the
  agents it covers (at most one per agent type), which is a fact about the
  agent's native config file, not about reach. The boot self-check exists
  precisely because that flag can disagree with the file. Callers that want
  "the active connection for this agent" intersect the two themselves.
"""

from __future__ import annotations

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


def projection_targets(
    resource: Resource, cfg: ProviderConfig, agents: list[Resource]
) -> list[AgentType]:
    """The agent types ``resource`` actually projects a key into.

    The configured reach, intersected with the user's ``enabled`` switch: a
    disabled connection projects into nothing, whatever else it says.
    """
    if not resource.enabled:
        return []
    return scoped_targets(resource, cfg, agents)


__all__ = ["projection_targets", "scoped_targets"]
