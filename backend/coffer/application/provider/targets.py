"""Which agents a connection projects into (ADR per-agent-resource-scope).

Five callers, two questions: the switch (``ProviderService``), the per-agent
key lookup the turn machinery does, the post-import projection reconcile and
the boot self-heal all want the effective projection; the management surface
wants the configured reach. Before scope reached this kind the answer lived in the
config as ``compatible_agents``; it is now the resource's framework-level
``scope``, and this module is the single seam where those agent-name strings
are hydrated into ``AgentType`` — keeping the provider's own config module
independent of the agent kind.

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
  every agent, per the framework; a connection created since scope reached this
  kind always carries a concrete list.
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

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.scope import agent_axis_admits


def scoped_targets(resource: Resource, cfg: ProviderConfig) -> list[AgentType]:
    """The agent types ``resource`` is CONFIGURED to cover, in ``AgentType`` order.

    A keyless (ollama) connection returns nothing whatever its scope says: it
    is Coffer's internal engine's endpoint and there is no key to write into an
    agent's config, so it covers no agent even in principle. That used to be a
    config-level validation rule; it is enforced here instead, because scope
    lives outside the config and the rule is about projection, not about the
    config's shape.

    ``enabled`` is not consulted — see this module's docstring for why the
    configured reach and the effective projection are kept apart.

    Only the scope's AGENT axis is read. "Which agent types does this
    connection cover" is a question about agents, and the answer must be the
    same wherever it is asked — the management surface renders it as the
    connection's chips, and a converged vault shows the same connection on
    every machine. Machine-axis enforcement, where a kind needs it, belongs at
    that kind's own activation gate (``channel``'s runtime), not inside a
    reach description.
    """
    if cfg.protocol is Protocol.OLLAMA:
        return []
    return [t for t in AgentType if agent_axis_admits(resource.scope, t.value)]


def projection_targets(resource: Resource, cfg: ProviderConfig) -> list[AgentType]:
    """The agent types ``resource`` actually projects a key into.

    The configured reach, intersected with the user's ``enabled`` switch: a
    disabled connection projects into nothing, whatever else it says.
    """
    if not resource.enabled:
        return []
    return scoped_targets(resource, cfg)


__all__ = ["projection_targets", "scoped_targets"]
