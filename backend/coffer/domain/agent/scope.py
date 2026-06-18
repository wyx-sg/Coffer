"""Per-agent MCP server scope (spec 001/004, ADR-026).

An agent's scope decides which registered MCP servers the gateway exposes to
that agent. ``auto`` means every enabled server (the default, and the legacy
whole-gateway-per-agent behaviour); ``selected`` means only the servers named in
the allowlist. Enforced by the gateway session; managed from the agent detail
page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ScopeMode = Literal["auto", "selected"]


@dataclass(frozen=True)
class AgentMcpScope:
    """An agent's MCP server scope: its mode and (when selected) its allowlist."""

    agent_name: str
    mode: ScopeMode
    servers: tuple[str, ...]  # allowlisted mcp_server names; empty unless selected
