"""Machine-readable slice of the FR-003a capability matrix.

The full matrix lives in the spec (spec 004 FR-003a) and the per-facet sources
of truth live where each facet is implemented: plugin management in the
descriptor manifest, transcript layouts in ``domain/distill/locations``,
provider projection targets in ``domain/provider/projection``. This module
composes the three booleans the UI needs so surfaces can render a uniform
"not supported" state (agent detail tabs) or omit an agent from cross-resource
pickers (the connection form) without hardcoding type lists.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.types import AgentType
from coffer.domain.distill.locations import supports_transcripts
from coffer.domain.provider.projection import target_for_agent


@dataclass(frozen=True)
class AgentCapabilities:
    """Per-facet support flags for one agent type."""

    plugins: bool
    transcripts: bool
    connections: bool


def capabilities_for(agent_type: AgentType) -> AgentCapabilities:
    return AgentCapabilities(
        plugins=descriptor_for(agent_type).plugins is not None,
        transcripts=supports_transcripts(agent_type.value),
        connections=target_for_agent(agent_type) is not None,
    )
