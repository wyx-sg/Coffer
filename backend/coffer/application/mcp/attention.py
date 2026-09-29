"""What about the registered MCP servers needs a person (the Overview list).

Three signals, each one the backend already records or can check cheaply:

- ``mcp_failing`` — the persisted health row the per-server test wrote says
  ``failing``;
- ``mcp_missing_launcher`` — a stdio server's launcher does not resolve on this
  machine (a server synced from another machine, its runner not installed
  here). The failing state it causes is then not reported beside it: both
  point at the same test, and the launcher is the cause;
- ``mcp_missing_secret`` — a credential ref the server's config cites is not in
  the credential store. One item per missing ref.

Only enabled servers are asked: a disabled one is not expected to work.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.application.mcp.runner_detect import missing_runner_of
from coffer.domain.resource import Resource

KIND = "mcp_server"


class McpResourcesPort(Protocol):
    """The kind-agnostic resource service, as far as this source reads it."""

    async def cited_credential_refs(self) -> Mapping[str, Sequence[Resource]]: ...

    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> Sequence[Resource]: ...


class McpHealthPort(Protocol):
    """The persisted per-server health row: ``(status, checked_at)``."""

    async def get(self, resource_uid: str) -> tuple[str, datetime] | None: ...


class CredentialPresencePort(Protocol):
    def exists(self, ref: str) -> bool: ...


def _test_action(uid: str) -> AttentionAction:
    return AttentionAction(
        verb="test", method="POST", path=f"/api/v1/resources/mcp_server/{uid}/test"
    )


def _title(resource: Resource) -> str:
    return resource.title or resource.name


class McpAttentionSource:
    name = "mcp_server"
    feature: str | None = None

    def __init__(
        self,
        *,
        resources: McpResourcesPort,
        health: McpHealthPort,
        credentials: CredentialPresencePort,
        runner_missing: Callable[[dict[str, Any]], str | None] = missing_runner_of,
    ) -> None:
        self._resources = resources
        self._health = health
        self._credentials = credentials
        self._runner_missing = runner_missing

    async def items(self) -> Sequence[AttentionItem]:
        servers = await self._resources.list(kind=KIND, enabled=True)
        if not servers:
            return []
        out: list[AttentionItem] = []
        for server in servers:
            out.extend(await self._launch_items(server))
        out.extend(await self._secret_items({s.uid: s for s in servers}))
        return out

    async def _launch_items(self, server: Resource) -> list[AttentionItem]:
        runner = await asyncio.to_thread(self._runner_missing, server.config)
        if runner is not None:
            return [
                AttentionItem(
                    kind=KIND,
                    uid=server.uid,
                    title=_title(server),
                    reason_code="mcp_missing_launcher",
                    reason=f"Its launcher `{runner}` is not installed on this machine.",
                    severity=Severity.ERROR,
                    action=_test_action(server.uid),
                )
            ]
        health = await self._health.get(server.uid)
        if health is None or health[0] != "failing":
            return []
        return [
            AttentionItem(
                kind=KIND,
                uid=server.uid,
                title=_title(server),
                reason_code="mcp_failing",
                reason="Its last connection test failed.",
                severity=Severity.ERROR,
                action=_test_action(server.uid),
                since=health[1],
            )
        ]

    async def _secret_items(self, enabled: dict[str, Resource]) -> list[AttentionItem]:
        out: list[AttentionItem] = []
        cited = await self._resources.cited_credential_refs()
        for ref in sorted(cited):
            citers = [enabled[r.uid] for r in cited[ref] if r.uid in enabled]
            if not citers or await asyncio.to_thread(self._credentials.exists, ref):
                continue
            for server in citers:
                out.append(
                    AttentionItem(
                        kind=KIND,
                        uid=server.uid,
                        title=_title(server),
                        reason_code="mcp_missing_secret",
                        reason=f"The credential `{ref}` it uses is not stored on this machine.",
                        severity=Severity.ERROR,
                        # The credential page's own write, with the ref and no
                        # value: the person supplies the secret there.
                        action=AttentionAction(
                            verb="set_secret",
                            method="POST",
                            path="/api/v1/credentials",
                            body={"ref": ref},
                        ),
                    )
                )
        return out


__all__ = [
    "CredentialPresencePort",
    "McpAttentionSource",
    "McpHealthPort",
    "McpResourcesPort",
]
