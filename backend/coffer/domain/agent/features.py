"""What Coffer can do with an agent of a given type, as a list of feature names.

Every name follows from the descriptor and its bound facets, never from a
hand-written table (agent-capability design option A): a type gets ``chat``
only once it has a driver, ``provider`` only once it has a provider
projection. Surfaces render by this list instead of by the agent's name, so a
type that lacks a facet simply has fewer tabs and pickers.
"""

from __future__ import annotations

from collections.abc import Collection

from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.types import AgentType

#: Every feature name, in the order surfaces list them.
FEATURES: tuple[str, ...] = (
    "mcp",
    "skills",
    "provider",
    "chat",
    "sessions",
    "plugins",
    "hooks",
)


def agent_features(
    catalog: AgentCatalog,
    agent_type: AgentType,
    *,
    session_types: Collection[AgentType] = (),
) -> list[str]:
    """The features ``agent_type`` has, in :data:`FEATURES` order.

    ``session_types`` names the types whose own sessions Coffer can list (the
    session sources are bound in infrastructure, so the composition root
    passes them in)."""
    d = catalog.get(agent_type)
    have = {
        "mcp": d.mcp is not None,
        # Every type is delivered skills (its projection's SKILL entry).
        "skills": True,
        "provider": catalog.provider_projection(agent_type) is not None,
        "chat": catalog.driver(agent_type) is not None,
        "sessions": agent_type in session_types,
        "plugins": d.plugins is not None,
        "hooks": bool(d.hook_source_keys),
    }
    return [f for f in FEATURES if have[f]]


__all__ = ["FEATURES", "agent_features"]
