"""Bind every agent mechanism to the agent it serves (ADR
agent-mechanisms-are-optional-facets-on-the-descriptor).

The descriptor table is pure data; the implementations of its four facets
live in four different kinds — the provider translation in the provider kind,
the memory reader in the memory kind, the driver in the
chat kind, the dependency probe in the agent kind. This is the one place that
sees all of them, so this is where they meet. Each implementation declares
its own agent; this module only lists them, and never says which is which.
"""

from __future__ import annotations

from coffer.domain.agent.descriptor import AGENT_DESCRIPTORS, AgentDescriptor
from coffer.domain.agent.facets import AgentCatalog, DependencyProbe, bind_facets
from coffer.domain.provider.agent_projection import PROVIDER_PROJECTIONS
from coffer.infrastructure.agent.program_probe import ProgramProbe, UserPath
from coffer.infrastructure.chat.drivers import DRIVERS
from coffer.infrastructure.memory.readers import MEMORY_READERS


def build_agent_catalog(*, user_path: UserPath | None = None) -> AgentCatalog:
    """The descriptor table with every facet bound. Built once per app."""
    path = user_path or UserPath()

    def _probe(d: AgentDescriptor) -> DependencyProbe | None:
        return ProgramProbe(d.program, user_path=path) if d.program else None

    return bind_facets(
        AGENT_DESCRIPTORS,
        providers=PROVIDER_PROJECTIONS,
        drivers=DRIVERS,
        memory_readers=MEMORY_READERS,
        probe_for=_probe,
    )


__all__ = ["build_agent_catalog"]
