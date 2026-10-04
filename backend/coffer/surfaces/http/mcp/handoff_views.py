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

from coffer.application.mcp.handoff import (
    STDERR_LINES,
    call_failure_handoff,
    diagnose_handoff,
    launcher_handoff,
)
from coffer.application.mcp.runner_detect import missing_runner_of
from coffer.domain.resource import Resource
from coffer.infrastructure.logging.upstream_tail import read_upstream_tail
from coffer.infrastructure.platform.host import machine_label

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


def launcher_prompt(resource: Resource, runner: str) -> str:
    return launcher_handoff(
        name=resource.name,
        config=resource.config,
        runner=runner,
        machine=_machine(),
        path=_launch_path(resource.config),
    )


def diagnose_prompt(
    resource: Resource, *, error: str | None, stderr: Sequence[str] | None = None
) -> str:
    """The diagnosis prompt. ``stderr`` is what a test just captured; without
    it the server's own log file is quoted."""
    lines, log_path = _log_tail(resource)
    return diagnose_handoff(
        name=resource.name,
        config=resource.config,
        error=error,
        stderr=list(stderr) if stderr else lines,
        machine=_machine(),
        log_path=log_path,
    )


def call_failure_prompt(
    *,
    server: str,
    tool: str,
    error: str | None,
    status: str,
    failures_24h: int,
    session_id: str | None,
    call_id: int,
) -> str:
    """The prompt for one call its server never answered (the Activity drawer)."""
    return call_failure_handoff(
        server=server,
        tool=tool,
        error=error,
        status=status,
        failures_24h=failures_24h,
        session_id=session_id,
        call_id=call_id,
        machine=_machine(),
    )


def unsaved_test_prompt(
    *, name: str, config: dict[str, Any], error: str | None, stderr: Sequence[str]
) -> str:
    """The prompt for a failed test of a config that is not saved (Add / Edit
    dialogs): the launcher to install when it is not found here, else the cause
    to find from the error and stderr. ``config`` carries no secret value."""
    runner = missing_runner_of(config)
    if runner is not None:
        return launcher_handoff(
            name=name,
            config=config,
            runner=runner,
            machine=_machine(),
            path=_launch_path(config),
            saved=False,
        )
    return diagnose_handoff(
        name=name,
        config=config,
        error=error,
        stderr=list(stderr),
        machine=_machine(),
        saved=False,
    )


def host_machine() -> str:
    """The machine label every hand-off prompt carries."""
    return _machine()


class McpHandoffs:
    """:class:`~coffer.application.mcp.attention.McpHandoffPort` over this module."""

    def launcher(self, server: Resource, runner: str) -> str:
        return launcher_prompt(server, runner)

    def diagnose(self, server: Resource) -> str:
        return diagnose_prompt(server, error=None)


__all__ = [
    "McpHandoffs",
    "diagnose_prompt",
    "host_machine",
    "launcher_prompt",
    "unsaved_test_prompt",
]
