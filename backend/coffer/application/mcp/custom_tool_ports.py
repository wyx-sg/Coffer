"""Ports of the custom-tool slice of the MCP kind (design add-http-custom-tools).

A tool's reach override is machine-local state kept beside, not inside, the
group's config (spec mcp-gateway "Switch off or narrow one custom tool"): the
config travels with sync and reach does not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from coffer.domain.mcp.capability import MCPInvocation
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.secrets import SecretApproval, SecretDestination


class ToolReachRepoPort(Protocol):
    """Per-tool reach overrides: ``(group uid, tool) -> agent uids``."""

    async def overrides_for(self, resource_uids: Sequence[str]) -> dict[str, dict[str, list[str]]]:
        """``{group uid: {tool: [agent uid, …]}}`` for the groups asked about."""
        ...

    async def set_override(self, resource_uid: str, tool: str, agents: list[str] | None) -> None:
        """Set a tool's override, or clear it with ``None``."""
        ...

    async def delete_tools(self, resource_uid: str, tools: Sequence[str]) -> None: ...

    async def delete_group(self, resource_uid: str) -> None: ...


class ToolOutcomesPort(Protocol):
    """The invocation log, as far as the custom tools page reads it."""

    async def tool_outcomes(
        self, *, resource_uids: list[str], since: datetime
    ) -> dict[str, dict[str, tuple[int, int]]]: ...

    async def last_tool_call(
        self, resource_uid: str, *, since: datetime
    ) -> MCPInvocation | None: ...


class SecretPresencePort(Protocol):
    def exists(self, ref: str) -> bool: ...


class BoundaryCheckPort(Protocol):
    """``SecretBoundary.check``: the approvals a destination still waits on."""

    def check(
        self, dest: SecretDestination, refs: Mapping[str, str], *, actor: str = "system"
    ) -> list[SecretApproval]: ...


class OpenApiSourcePort(Protocol):
    async def fetch(self, url: str) -> tuple[str, str]:
        """``(final URL, text)``; raises ``OpenApiUnreadable``."""
        ...

    def parse(self, text: str) -> Any:
        """JSON or YAML into a mapping; raises ``OpenApiUnreadable``."""
        ...


@dataclass(frozen=True)
class ToolTestOutcome:
    """One test run of a draft tool (nothing saved, nothing logged)."""

    ok: bool
    duration_ms: int
    url: str | None = None
    status: int | None = None
    status_line: str | None = None
    body: str = ""
    truncated: bool = False
    content_type: str | None = None
    error: str | None = None
    #: How it failed before an answer: ``request``, ``timeout``, ``connect``
    #: or ``blocked``; ``None`` when the API answered.
    failure: str | None = None


class CustomToolRunnerPort(Protocol):
    async def run(
        self,
        transport: HttpApiTransport,
        tool: HttpApiTool,
        arguments: dict[str, Any],
        overlay: dict[str, str],
    ) -> ToolTestOutcome: ...

    async def run_unsaved(
        self, transport: HttpApiTransport, tool: HttpApiTool, arguments: dict[str, Any]
    ) -> ToolTestOutcome:
        """A request of a group that is not saved yet: its base URL was typed
        into a form, so it passes the SSRF guard first, and no secret is sent."""
        ...
