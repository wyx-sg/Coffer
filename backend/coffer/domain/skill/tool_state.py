"""The MCP servers and custom-tool groups a skill's ``requires: tools:`` names,
as the Requires tab shows them (spec skill-manager "Declare the tools a skill
requires").

A custom-tool group and an MCP server are both ``mcp_server`` resources; they
differ by transport. The state is the resource's own: off when it is switched
off, failing when its last connection test failed, healthy otherwise. Its reach
is carried beside the state, so a skill can say which of the agents it is
delivered to cannot call it (ADR a-skills-tool-is-checked-against-each-agent-
that-gets-the-skill)."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from coffer.domain.skill.requirements import ToolRequirement


class ToolKind(StrEnum):
    MCP_SERVER = "mcp_server"
    CUSTOM_TOOLS = "custom_tools"


class ToolStatus(StrEnum):
    HEALTHY = "healthy"
    OFF = "off"
    FAILING = "failing"


@dataclass(frozen=True)
class ToolState:
    uid: str
    name: str
    kind: ToolKind
    status: ToolStatus
    #: The agents (uids) its reach names; ``None`` when it reaches every agent.
    reach: frozenset[str] | None = None

    def misses(self, agents: Collection[str]) -> list[str]:
        """Which of ``agents`` it does not reach. A tool that is off is
        reported as off, not as missing every agent."""
        if self.reach is None or self.status is ToolStatus.OFF:
            return []
        return sorted(a for a in agents if a not in self.reach)


@dataclass(frozen=True)
class ResolvedTool:
    requirement: ToolRequirement
    state: ToolState


def resolve_tools(
    requirements: Sequence[ToolRequirement], states: Mapping[str, ToolState]
) -> tuple[list[ResolvedTool], list[str]]:
    """The declared tools Coffer knows, and a warning for each it does not."""
    found: list[ResolvedTool] = []
    warnings: list[str] = []
    for req in requirements:
        state = states.get(req.name)
        if state is None:
            warnings.append(
                f"requires tool {req.name}: no MCP server or custom-tool group has that name; "
                "skipped"
            )
        else:
            found.append(ResolvedTool(req, state))
    return found, warnings


__all__ = ["ResolvedTool", "ToolKind", "ToolState", "ToolStatus", "resolve_tools"]
