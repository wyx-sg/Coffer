"""The MCP server hand-offs as the routes and the Overview hand them over.

``application/mcp/handoff.py`` writes the prompts from facts; this is where the
facts that live on the host are read — the machine's OS and architecture, the
``PATH`` a started server gets, and the tail of the server's own log file —
so the status read, the test route and the attention list all say the same
words (spec mcp-gateway "Name a missing stdio launcher", "Hand a failing MCP
server's diagnosis to an agent").
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from functools import cache
from typing import Any

from coffer.application.mcp.handoff import STDERR_LINES, server_handoff
from coffer.application.mcp.runner_detect import missing_runner_of
from coffer.application.mcp.server_status import failure_run
from coffer.domain.resource import Resource
from coffer.infrastructure.logging.upstream_tail import read_upstream_tail
from coffer.infrastructure.platform.host import machine_label

#: How many of a server's newest calls are read for its current failure run.
_ERROR_LOOKBACK = 20

#: The OS and architecture do not change while the daemon runs.
_machine = cache(machine_label)


def _launch_path(config: dict[str, Any]) -> str:
    """The ``PATH`` a started server gets: its own ``env`` entry, else the daemon's."""
    transport = config.get("transport")
    env = transport.get("env") if isinstance(transport, dict) else None
    if isinstance(env, dict) and isinstance(env.get("PATH"), str):
        return str(env["PATH"])
    return os.environ.get("PATH", "")


def _log_tail(resource: Resource) -> tuple[list[str], str | None]:
    """The server's newest log lines, oldest first, and the file they came from."""
    transport = resource.config.get("transport")
    if not isinstance(transport, dict) or transport.get("type") != "stdio":
        return [], None
    tail = read_upstream_tail(resource.name, STDERR_LINES)
    return [line.text for line in reversed(tail.lines)], (
        str(tail.path) if tail.path is not None else None
    )


def server_prompt(
    resource: Resource,
    *,
    error: str | None,
    runner: str | None = None,
    stderr: Sequence[str] | None = None,
) -> str:
    """The server's one hand-off. ``runner`` is its launcher when it is not
    found here; ``stderr`` is what a test just captured, without it the
    server's own log file is quoted."""
    lines, log_path = _log_tail(resource)
    return server_handoff(
        name=resource.name,
        config=resource.config,
        error=error,
        stderr=list(stderr) if stderr else lines,
        machine=_machine(),
        log_path=log_path,
        runner=runner,
        path=_launch_path(resource.config) if runner else "",
    )


def unsaved_test_prompt(
    *, name: str, config: dict[str, Any], error: str | None, stderr: Sequence[str]
) -> str:
    """The hand-off for a failed test of a config that is not saved (Add / Edit
    dialogs). ``config`` carries no secret value."""
    runner = missing_runner_of(config)
    return server_handoff(
        name=name,
        config=config,
        error=error,
        stderr=list(stderr),
        machine=_machine(),
        saved=False,
        runner=runner,
        path=_launch_path(config) if runner else "",
    )


def host_machine() -> str:
    """The machine label every hand-off prompt carries."""
    return _machine()


class McpHandoffs:
    """:class:`~coffer.application.mcp.attention.McpHandoffPort` over this module."""

    async def last_error(self, server_uid: str) -> str | None:
        # Imported here: the invocation repo is set once the gateway is built,
        # after this module is imported.
        from coffer.surfaces.http.mcp.dependencies import get_invocation_repo_optional

        repo = get_invocation_repo_optional()
        if repo is None:
            return None
        run = failure_run(await repo.query(resource_uid=server_uid, limit=_ERROR_LOOKBACK))
        return run.last_error if run else None

    def server(self, server: Resource, *, error: str | None, runner: str | None) -> str:
        return server_prompt(server, error=error, runner=runner)


__all__ = [
    "McpHandoffs",
    "host_machine",
    "server_prompt",
    "unsaved_test_prompt",
]
