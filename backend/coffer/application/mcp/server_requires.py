"""What an MCP server needs from this machine, worked out from its config.

Spec mcp-gateway "Show what an MCP server requires". The Requires section of a
server's page lists, from the command and settings alone:

- the **launcher CLI** a stdio server starts with (``npx``, ``uvx``, ``docker``,
  ``bunx``, ``node``, ``python``, …), with whether it is found on this machine
  and its version — checked the way the CLIs page checks a command, and cached
  per launcher so reading a page never runs a program twice;
- every **secret** the config cites — from ``secret_refs`` (an environment
  variable or header whose value is a stored secret) or a ``coffer://secret/<name>``
  written in a plain value — and whether it is set on this machine, missing
  from it, or waiting for an approval.

An HTTP server has no launcher. Reading is cheap and never starts the server.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from coffer.application.mcp.custom_tool_ports import BoundaryCheckPort, SecretPresencePort
from coffer.domain.mcp.secret_target import mcp_destination
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Resource
from coffer.domain.secrets import cited_secret_names, secret_ref, standalone_name


class CommandProbePort(Protocol):
    """The CLIs page's command check (``infrastructure.skill.command_probe``)."""

    def locate(self, command: str) -> str | None: ...

    def version(self, path: str) -> str | None: ...


RequirementKind = Literal["cli", "secret"]
RequirementStatus = Literal["found", "not_found", "set", "missing", "waiting_approval"]


@dataclass(frozen=True)
class ServerRequirement:
    kind: RequirementKind
    #: The launcher command, or the environment variable / header that holds the secret.
    name: str
    status: RequirementStatus
    #: A CLI's version when it printed one.
    version: str | None = None
    #: A secret's name on the Secrets page (``None`` for a CLI).
    secret: str | None = None


class ServerRequirements:
    def __init__(
        self,
        *,
        probe: CommandProbePort,
        secrets: SecretPresencePort,
        boundary: Callable[[], BoundaryCheckPort | None],
    ) -> None:
        self._probe = probe
        self._secrets = secrets
        self._boundary = boundary
        #: launcher -> version of one found on this machine. A launcher that is
        #: not found is looked up again on every read: finding it is one PATH
        #: lookup, and installing it must show at once.
        self._versions: dict[str, str | None] = {}

    async def of(self, resource: Resource) -> list[ServerRequirement]:
        try:
            config = MCPServerConfig.model_validate(resource.config)
        except Exception:
            return []
        out: list[ServerRequirement] = []
        transport = config.transport
        if transport.type == "stdio" and transport.command.strip():
            out.append(await self._launcher(transport.command.strip()))
        out.extend(await self._secrets_of(resource, config))
        return out

    async def _launcher(self, command: str) -> ServerRequirement:
        name = command.rsplit("/", 1)[-1] or command
        path = await asyncio.to_thread(self._probe.locate, command)
        if path is None:
            self._versions.pop(command, None)
            return ServerRequirement(kind="cli", name=name, status="not_found")
        if command not in self._versions:
            self._versions[command] = await asyncio.to_thread(self._probe.version, path)
        return ServerRequirement(
            kind="cli", name=name, status="found", version=self._versions[command]
        )

    async def _secrets_of(
        self, resource: Resource, config: MCPServerConfig
    ) -> list[ServerRequirement]:
        transport = config.transport
        if transport.type == "http_api":
            return []
        cited: dict[str, str] = dict(transport.secret_refs)
        plain: Mapping[str, str] = transport.env if transport.type == "stdio" else transport.headers
        for slot, value in plain.items():
            for name in sorted(cited_secret_names(value)):
                cited.setdefault(
                    slot if slot not in cited else f"{slot} ({name})", secret_ref(name)
                )
        if not cited:
            return []
        exists = {
            slot: await asyncio.to_thread(self._secrets.exists, ref) for slot, ref in cited.items()
        }
        waiting: set[str] = set()
        boundary = self._boundary()
        present = {s: r for s, r in cited.items() if exists[s] and s in transport.secret_refs}
        if boundary is not None and present:
            dest = mcp_destination(resource.uid, resource.name, config)
            pending = await asyncio.to_thread(boundary.check, dest, present)
            waiting = {a.slot for a in pending if a.slot}
        rows: list[ServerRequirement] = []
        for slot, ref in cited.items():
            status: RequirementStatus = (
                "missing" if not exists[slot] else "waiting_approval" if slot in waiting else "set"
            )
            rows.append(
                ServerRequirement(
                    kind="secret", name=slot, status=status, secret=standalone_name(ref) or ref
                )
            )
        return rows


__all__ = ["RequirementKind", "RequirementStatus", "ServerRequirement", "ServerRequirements"]
