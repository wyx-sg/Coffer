"""Missing-runner detection for stdio MCP servers (spec mcp-gateway amendment).

A synced stdio server references a launcher command (``uvx``, ``npx``, …)
that may not exist on this machine — the server then shows as failing with
no hint that the fix is "install the runner". Detection is a PATH lookup on
the command's basename; installing the runner is the user's own step (Coffer
manages configuration, it does not install software).
"""

from __future__ import annotations

import pathlib
import shutil
from typing import Any

from coffer.domain.mcp.server_config import MCPServerConfig


def missing_runner(command: str) -> str | None:
    """The command's basename when it cannot be resolved on this machine.

    An absolute path checks existence directly; a bare name goes through
    PATH. None = the runner resolves (whatever health says is not this)."""
    if not command:
        return None
    path = pathlib.Path(command)
    if path.is_absolute():
        return None if path.exists() else path.name
    return None if shutil.which(command) else path.name


def missing_runner_of(config: dict[str, Any]) -> str | None:
    """:func:`missing_runner` for an mcp_server's config: the launcher of a
    stdio server that does not resolve here, else None (an HTTP server has no
    launcher, and a config that does not parse says nothing about one)."""
    try:
        parsed = MCPServerConfig.model_validate(config)
    except Exception:
        return None
    if parsed.transport.type != "stdio":
        return None
    return missing_runner(parsed.transport.command)
