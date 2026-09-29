"""Where an MCP server's secrets go, as the secret boundary sees it.

The target is what an approval is pinned to (spec credentials "Hold a secret
for a new destination until a person approves it"). For a stdio server it is
the whole command Coffer spawns — command, arguments, working directory and
the non-secret environment, because any of them can change what the process
does with the secret it is handed (``NODE_OPTIONS=--require …`` is enough).
For an HTTP server it is the URL the header is sent to.

A stdio server receives its secrets in its initial environment, which any
process of the same user can read (``ps eww``), so such a server is reported as
readable by other processes on this Mac (ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new, "What stays
exposed").
"""

from __future__ import annotations

import shlex

from coffer.domain.mcp.server_config import HttpTransport, MCPServerConfig, StdioTransport
from coffer.domain.secrets import SecretDestination

KIND = "mcp_server"


def secret_target(transport: StdioTransport | HttpTransport) -> str:
    if isinstance(transport, HttpTransport):
        return f"http {transport.url}"
    parts = [f"stdio {shlex.join([transport.command, *transport.args])}"]
    if transport.cwd:
        parts.append(f"in {transport.cwd}")
    if transport.env:
        parts.append("with " + " ".join(f"{k}={v}" for k, v in sorted(transport.env.items())))
    return " ".join(parts)


def mcp_destination(uid: str, name: str, config: MCPServerConfig) -> SecretDestination:
    return SecretDestination(kind=KIND, uid=uid, target=secret_target(config.transport), label=name)


def secrets_readable_by_local_processes(config: MCPServerConfig) -> bool:
    """A stdio server whose environment carries a secret."""
    return isinstance(config.transport, StdioTransport) and bool(config.transport.credential_refs)
