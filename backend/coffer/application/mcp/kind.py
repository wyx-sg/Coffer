"""MCP-specific Kind wiring used by the composition root."""

from __future__ import annotations

import asyncio
import contextlib

from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind, ResourceRef


def make_mcp_kind(supervisor_for: dict[str, SubprocessSupervisor]) -> Kind:
    """Construct the `mcp_server` Kind with an on_delete hook.

    `supervisor_for` is a process-local registry of session-id -> supervisor;
    on resource delete we walk it and evict the matching server from each
    live session. This is best-effort — sessions may not have the server
    spawned yet (no-op) or the connection may have already crashed
    (suppressed).
    """

    def on_delete(ref: ResourceRef) -> None:
        # Synchronous hook called by ResourceService.delete BEFORE persistence.
        # We can't await inside a sync hook; schedule an async eviction in the
        # background if a running loop exists.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop (e.g., a sync CLI delete path) — nothing to do.
            return

        async def _evict_all() -> None:
            for supervisor in list(supervisor_for.values()):
                with contextlib.suppress(Exception):
                    await supervisor.evict(ref.name)

        _task = loop.create_task(_evict_all())  # noqa: RUF006  # best-effort fire-and-forget

    return Kind(
        name="mcp_server",
        display_name="MCP Server",
        config_schema=MCPServerConfig,
        on_delete=on_delete,
    )
