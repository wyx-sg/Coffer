"""Where an MCP server's secrets go, as the secret boundary sees it.

The target is what an approval is pinned to (spec secret "Hold a secret
for a new destination until a person approves it"). For a stdio server it is
the whole command Coffer spawns — command, arguments, working directory and
the non-secret environment, because any of them can change what the process
does with the secret it is handed (``NODE_OPTIONS=--require …`` is enough).
For an HTTP server it is the URL the header is sent to, and for a custom-tool
group (the ``http_api`` transport) each enabled ENVIRONMENT is a destination of
its own: the group's uid, the label ``<group> · <environment>``, the target
``http_api <base URL>`` and slots ``<key>:<header>`` (design
align-cli-with-ui-and-add-tool-environments D6) — so approving one environment
approves nothing for another, and moving one environment's URL asks again for
that environment only. A group lifted from before environments keeps the bare
header as its slot, so its approvals survive.

A stdio server receives its secrets in its initial environment, which any
process of the same user can read (``ps eww``), so such a server is reported as
readable by other processes on this Mac (ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new, "What stays
exposed").
"""

from __future__ import annotations

import shlex

from coffer.domain.mcp.http_api import HttpApiTransport, http_api_target
from coffer.domain.mcp.http_api_environment import HttpApiEnvironment
from coffer.domain.mcp.server_config import (
    AnyTransport,
    HttpTransport,
    MCPServerConfig,
)
from coffer.domain.secrets import SecretDestination

KIND = "mcp_server"


def secret_target(transport: AnyTransport) -> str:
    if isinstance(transport, HttpApiTransport):
        # The whole group, for a reader that wants one line (an audit summary):
        # every environment's base URL, in order.
        return "; ".join(http_api_target(e) for e in transport.environments)
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


def environment_destination(uid: str, name: str, env: HttpApiEnvironment) -> SecretDestination:
    """One environment of a custom-tool group, as the secret boundary sees it."""
    return SecretDestination(
        kind=KIND, uid=uid, target=http_api_target(env), label=f"{name} · {env.name}"
    )


def mcp_destinations(
    uid: str, name: str, config: MCPServerConfig
) -> list[tuple[SecretDestination, dict[str, str]]]:
    """Every destination of a server with the refs each slot cites; empty when
    it sends no secret. A custom-tool group has one per enabled environment."""
    transport = config.transport
    if isinstance(transport, HttpApiTransport):
        return [
            (environment_destination(uid, name, env), env.slot_refs())
            for env in transport.environments
            if env.enabled and env.secret_refs
        ]
    refs = dict(transport.secret_refs)
    return [(mcp_destination(uid, name, config), refs)] if refs else []
