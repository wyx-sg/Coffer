"""What the custom tools page shows of a group: health, secret, 24-hour summary.

Spec mcp-gateway "Manage custom tools on REST and the command line"; design
add-http-custom-tools §9. Read-only: it reads the group's row and config, the
invocation log, the secret store and the secret boundary, and writes
nothing but what ``SecretBoundary.check`` records (a pending approval appears
the moment a change needs one, as the approvals list does).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from coffer.application.mcp.custom_tool_ports import (
    BoundaryCheckPort,
    SecretPresencePort,
    ToolOutcomesPort,
    ToolReachRepoPort,
)
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.secret_target import mcp_destination
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Resource
from coffer.domain.secrets import standalone_name

GroupHealth = Literal["failing", "attention", "healthy", "idle", "off"]
SecretState = Literal["none", "present", "missing", "pending_approval"]
#: The list's order: failing groups first (spec web-ui "Manage custom tools on
#: their own page"), switched-off ones last.
HEALTH_ORDER: dict[str, int] = {"failing": 0, "attention": 1, "healthy": 2, "idle": 3, "off": 4}
WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class ToolView:
    tool: HttpApiTool
    reach_override: list[str] | None
    calls: int
    failures: int


@dataclass(frozen=True)
class GroupView:
    resource: Resource
    transport: HttpApiTransport
    health: GroupHealth
    health_reason: str | None
    #: The worst state across the group's secret headers (missing, then
    #: waiting for approval, then present); ``none`` with no secret header.
    secret_state: SecretState
    #: Each secret header's own state, keyed by header name.
    header_states: dict[str, SecretState]
    pending_approvals: list[str]
    #: The names of the secrets whose approval is pending.
    pending_secrets: list[str]
    calls: int
    failures: int
    last_call_at: datetime | None
    tools: list[ToolView]


class GroupViewer:
    def __init__(
        self,
        *,
        reach: ToolReachRepoPort,
        outcomes: ToolOutcomesPort | None,
        secrets: SecretPresencePort | None,
        boundary: Callable[[], BoundaryCheckPort | None],
        clock: Callable[[], datetime],
    ) -> None:
        self._reach = reach
        self._outcomes = outcomes
        self._secrets = secrets
        self._boundary = boundary
        self._clock = clock

    async def _secret_states(
        self, resource: Resource, transport: HttpApiTransport
    ) -> tuple[dict[str, SecretState], list[str], list[str]]:
        """``(state per secret header, pending approval ids, pending secret names)``."""
        states: dict[str, SecretState] = {}
        present: dict[str, str] = {}
        for header, ref in transport.secret_refs.items():
            if self._secrets is not None and not await asyncio.to_thread(self._secrets.exists, ref):
                states[header] = "missing"
            else:
                states[header] = "present"
                present[header] = ref
        boundary = self._boundary()
        if boundary is None or not present:
            return states, [], []
        config = MCPServerConfig(transport=transport)
        dest = mcp_destination(resource.uid, resource.name, config)
        pending = await asyncio.to_thread(boundary.check, dest, present)
        for approval in pending:
            if approval.slot in states:
                states[approval.slot] = "pending_approval"
        names = [standalone_name(a.ref or "") or (a.ref or "") for a in pending]
        return states, [a.id for a in pending], names

    async def views(self, groups: list[tuple[Resource, HttpApiTransport]]) -> list[GroupView]:
        if not groups:
            return []
        uids = [r.uid for r, _ in groups]
        since = self._clock() - WINDOW
        overrides = await self._reach.overrides_for(uids)
        counts = (
            await self._outcomes.tool_outcomes(resource_uids=uids, since=since)
            if self._outcomes is not None
            else {}
        )
        out: list[GroupView] = []
        for resource, transport in groups:
            header_states, pending, pending_secrets = await self._secret_states(resource, transport)
            secret_state = _worst(header_states)
            last = (
                await self._outcomes.last_tool_call(resource.uid, since=since)
                if self._outcomes is not None
                else None
            )
            per_tool = counts.get(resource.uid, {})
            tools = [
                ToolView(
                    tool=t,
                    reach_override=overrides.get(resource.uid, {}).get(t.name),
                    calls=per_tool.get(t.name, (0, 0))[0],
                    failures=per_tool.get(t.name, (0, 0))[1],
                )
                for t in transport.tools
            ]
            health, reason = _health(resource, secret_state, last.status if last else None)
            out.append(
                GroupView(
                    resource=resource,
                    transport=transport,
                    health=health,
                    health_reason=reason,
                    secret_state=secret_state,
                    header_states=header_states,
                    pending_approvals=pending,
                    pending_secrets=pending_secrets,
                    calls=sum(c for c, _ in per_tool.values()),
                    failures=sum(f for _, f in per_tool.values()),
                    last_call_at=last.timestamp if last else None,
                    tools=tools,
                )
            )
        out.sort(key=lambda v: (HEALTH_ORDER[v.health], v.resource.name))
        return out


def _worst(states: dict[str, SecretState]) -> SecretState:
    for state in ("missing", "pending_approval", "present"):
        if state in states.values():
            return state
    return "none"


def _health(
    resource: Resource, secret_state: SecretState, last_status: str | None
) -> tuple[GroupHealth, str | None]:
    if not resource.enabled:
        return "off", None
    if last_status in ("error", "timeout"):
        return "failing", "last_call_failed"
    if secret_state == "missing":
        return "attention", "secret_missing"
    if secret_state == "pending_approval":
        return "attention", "approval_pending"
    if last_status == "ok":
        return "healthy", None
    return "idle", None


__all__ = ["HEALTH_ORDER", "GroupHealth", "GroupView", "GroupViewer", "SecretState", "ToolView"]
