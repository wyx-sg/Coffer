"""GET /api/v1/mcp/builtin — Coffer's own ``coffer`` server, described read-only.

Spec mcp-gateway "Describe the built-in coffer server". Every connected agent
reaches Coffer through one MCP endpoint the daemon serves itself; the MCP
servers page shows it last, under Built-in, beside the servers the person
added. It is not a registered resource — there is no row, nothing to edit or
remove — so this route builds it from what the daemon knows: the gateway's
built-in tool list (only the tools of switched-on features), the port it is
bound to, the agents whose config holds Coffer's entry, and the last 24 hours
of the invocation log, where built-in calls are recorded under the reserved
server id ``coffer`` (``domain.mcp.capability.BUILTIN_SERVER_UID``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX, BuiltinToolRegistry
from coffer.application.mcp.gateway_tool_search import tool_search_descriptor
from coffer.domain.mcp.capability import BUILTIN_SERVER_UID
from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
from coffer.surfaces.http import daemon_port
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.mcp.dependencies import get_invocation_repo
from coffer.surfaces.http.mcp.page_schemas import InvocationSummaryOut, invocation_summary_out

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"], dependencies=[Depends(require_token)])

#: The uids of the agents whose MCP config holds Coffer's own entry. Supplied
#: by the composition root, which is the one place that sees the agent kind.
ConnectedAgents = Callable[[], Awaitable[list[str]]]


@dataclass(frozen=True)
class BuiltinServerSource:
    tools: BuiltinToolRegistry
    connected_agents: ConnectedAgents


_source: BuiltinServerSource | None = None


def set_builtin_server_source(source: BuiltinServerSource | None) -> None:
    """Called by the composition root once on startup."""
    global _source
    _source = source


def get_builtin_server_source() -> BuiltinServerSource:
    """FastAPI Depends() target."""
    if _source is None:
        raise RuntimeError("built-in server source not initialised")
    return _source


class BuiltinToolOut(BaseModel):
    #: The bare name (``search_tools``).
    name: str
    #: What agents call it (``coffer__search_tools``).
    qualified_name: str
    description: str


class McpBuiltinServerOut(BaseModel):
    """Coffer's own MCP server. Read-only: it has no settings."""

    name: Literal["coffer"] = "coffer"
    #: The value its calls are recorded under — the ``uid`` filter of
    #: ``GET /api/v1/mcp/invocations`` for its Invocations tab.
    invocation_uid: str = BUILTIN_SERVER_UID
    transport: Literal["http"] = Field(
        default="http", description="Streamable HTTP, served by the daemon itself."
    )
    url: str = Field(description="The endpoint agents connect to.")
    status: Literal["healthy"] = Field(
        default="healthy", description="The daemon is answering, so its endpoint is."
    )
    checked_at: datetime = Field(description="When the daemon answered this read.")
    #: Every connected agent gets it; these are the agents connected now.
    reaches_all_connected_agents: bool = True
    connected_agent_uids: list[str]
    tools: list[BuiltinToolOut]
    tool_count: int
    #: The last 24 hours, in the shape the registered servers' Overview reads.
    summary: InvocationSummaryOut


def _tools(registry: BuiltinToolRegistry) -> list[BuiltinToolOut]:
    search = tool_search_descriptor()
    qualified = [(search["name"], search["description"])] + [
        (f"{COFFER_TOOL_PREFIX}{t.name}", t.description) for t in registry.list()
    ]
    return [
        BuiltinToolOut(
            name=q.removeprefix(COFFER_TOOL_PREFIX), qualified_name=q, description=d or ""
        )
        for q, d in qualified
    ]


@router.get("/builtin", response_model=McpBuiltinServerOut)
async def get_builtin_server(
    source: BuiltinServerSource = Depends(get_builtin_server_source),  # noqa: B008
    invocations: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
) -> McpBuiltinServerOut:
    """The ``coffer`` server: endpoint, tools, reach and the last 24 hours."""
    now = datetime.now(tz=UTC)
    summary = await invocations.summary(
        resource_uid=BUILTIN_SERVER_UID, since=now - timedelta(hours=24)
    )
    tools = _tools(source.tools)
    return McpBuiltinServerOut(
        url=f"http://127.0.0.1:{daemon_port.get_port()}/mcp",
        checked_at=now,
        connected_agent_uids=await source.connected_agents(),
        tools=tools,
        tool_count=len(tools),
        summary=invocation_summary_out(summary),
    )


__all__ = [
    "BuiltinServerSource",
    "ConnectedAgents",
    "McpBuiltinServerOut",
    "get_builtin_server_source",
    "router",
    "set_builtin_server_source",
]
