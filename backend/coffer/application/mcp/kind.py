"""MCP-specific Kind wiring used by the composition root."""

from __future__ import annotations

import contextlib

from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind, ResourceRef


def _validate_mcp_name(name: str) -> None:
    """Reject mcp_server names that would break tool/prompt namespacing.

    CODE-030: capabilities are exposed downstream as ``<server>__<tool>`` and
    parsed back by splitting on the first ``__``. A server name containing
    ``__`` makes that parse ambiguous (it would route to the wrong server, so
    the tool lists but can never be invoked). Reserve the separator.
    """
    if "__" in name:
        raise ValueError(
            f"mcp_server name {name!r} may not contain '__' "
            "(reserved as the tool/prompt namespace separator)"
        )


def make_mcp_kind(supervisor_for: dict[str, SubprocessSupervisor]) -> Kind:
    """Construct the `mcp_server` Kind with on_delete + name-validation hooks.

    `supervisor_for` is a process-local registry of session-id -> supervisor;
    on resource delete we walk it and evict the matching server from each
    live session. This is best-effort — sessions may not have the server
    spawned yet (no-op) or the connection may have already crashed
    (suppressed).
    """

    async def on_delete(ref: ResourceRef) -> None:
        # CODE-033: async hook AWAITED by ResourceService.delete BEFORE the row
        # is removed, so every live session's upstream connection for this
        # server is fully evicted before deletion completes — no in-flight call
        # can outlive the registration and leak the subprocess.
        for supervisor in list(supervisor_for.values()):
            with contextlib.suppress(Exception):
                await supervisor.evict(ref.name)

    return Kind(
        name="mcp_server",
        display_name="MCP Server",
        config_schema=MCPServerConfig,
        on_delete=on_delete,
        validate_name=_validate_mcp_name,
    )
