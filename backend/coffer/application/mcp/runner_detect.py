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
