"""Where an MCP server's secrets go, as the secret boundary sees it.

The target is what an approval is pinned to (spec secret "Hold a secret
for a new destination until a person approves it"). For a stdio server it is
the whole command Coffer spawns — command, arguments, working directory and
the non-secret environment, because any of them can change what the process
does with the secret it is handed (``NODE_OPTIONS=--require …`` is enough).
For an HTTP server it is the URL the header is sent to, and for a custom-tool
group (the ``http_api`` transport) the base URL its auth header goes to —
changing either is sending the secret somewhere new.

A stdio server receives its secrets in its initial environment, which any
process of the same user can read (``ps eww``), so such a server is reported as
readable by other processes on this Mac (ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new, "What stays
exposed").
"""

from __future__ import annotations

import shlex

from coffer.domain.mcp.http_api import HttpApiTransport, http_api_target
from coffer.domain.mcp.server_config import (
    AnyTransport,
    HttpTransport,
    MCPServerConfig,
)
from coffer.domain.secrets import SecretDestination

KIND = "mcp_server"


def secret_target(transport: AnyTransport) -> str:
    if isinstance(transport, HttpApiTransport):
        return http_api_target(transport)
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
