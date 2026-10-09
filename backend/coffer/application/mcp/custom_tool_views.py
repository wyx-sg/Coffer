"""What the custom tools page shows of a group: health, secret, 24-hour summary.

Spec mcp-gateway "Manage custom tools through REST and the Custom tools page"; design
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
)
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.http_api_environment import HttpApiEnvironment
from coffer.domain.mcp.secret_target import environment_destination
from coffer.domain.resource import Resource
from coffer.domain.secrets import SecretApproval, standalone_name

GroupHealth = Literal["failing", "attention", "healthy", "idle", "off"]
SecretState = Literal["none", "present", "missing", "rejected", "pending_approval"]
#: The list's order: failing groups first (spec web-ui "Manage custom tool groups on
#: their own page"), switched-off ones last.
HEALTH_ORDER: dict[str, int] = {"failing": 0, "attention": 1, "healthy": 2, "idle": 3, "off": 4}
WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class ToolView:
    tool: HttpApiTool
    calls: int
    failures: int


@dataclass(frozen=True)
class EnvironmentView:
    """One environment's secrets as the page shows them."""

    environment: HttpApiEnvironment
    #: The worst state of its secret headers; ``none`` with no secret header.
    secret_state: SecretState
    #: Each secret header's own state, keyed by header name.
    header_states: dict[str, SecretState]
    pending_approvals: list[str]
    pending_secrets: list[str]
    #: The refused approvals that block it until asked again, and their secrets.
    rejected_approvals: list[str]
    rejected_secrets: list[str]


@dataclass(frozen=True)
class GroupView:
    resource: Resource
    transport: HttpApiTransport
    health: GroupHealth
    health_reason: str | None
    #: The worst state across the enabled environments' secret headers
    #: (missing, then refused, then waiting for approval, then present);
    #: ``none`` with none.
    secret_state: SecretState
    environments: list[EnvironmentView]
    pending_approvals: list[str]
    #: The names of the secrets whose approval is pending.
    pending_secrets: list[str]
    rejected_approvals: list[str]
    #: The names of the secrets whose approval a person refused.
    rejected_secrets: list[str]
    calls: int
    failures: int
    last_call_at: datetime | None
    #: The newest call's status and error text, for the failing group's hand-off.
    last_call_status: str | None
    last_call_error: str | None
    tools: list[ToolView]


class GroupViewer:
    def __init__(
        self,
        *,
        outcomes: ToolOutcomesPort | None,
        secrets: SecretPresencePort | None,
        boundary: Callable[[], BoundaryCheckPort | None],
        clock: Callable[[], datetime],
    ) -> None:
        self._outcomes = outcomes
        self._secrets = secrets
        self._boundary = boundary
        self._clock = clock

    async def environment(self, resource: Resource, env: HttpApiEnvironment) -> EnvironmentView:
        """One environment's secret states: presence and pending approvals, never a value."""
        states: dict[str, SecretState] = {}
        present: dict[str, str] = {}
        for header, ref in env.secret_refs.items():
            if self._secrets is not None and not await asyncio.to_thread(self._secrets.exists, ref):
                states[header] = "missing"
            else:
                states[header] = "present"
                present[env.slot(header)] = ref
        boundary = self._boundary()
        if boundary is None or not present or not env.enabled:
            return EnvironmentView(env, _worst(states), states, [], [], [], [])
        dest = environment_destination(resource.uid, resource.name, env)
        # A refused approval is not waiting: it blocks until it is asked again.
        waiting = await asyncio.to_thread(boundary.check, dest, present)
        for approval in waiting:
            if approval.slot in present:
                refused = approval.status == "rejected"
                states[env.header_of(approval.slot)] = "rejected" if refused else "pending_approval"
        pending = [a for a in waiting if a.status != "rejected"]
        rejected = [a for a in waiting if a.status == "rejected"]
        return EnvironmentView(
            env,
            _worst(states),
            states,
            [a.id for a in pending],
            _names(pending),
            [a.id for a in rejected],
            _names(rejected),
        )

    async def views(self, groups: list[tuple[Resource, HttpApiTransport]]) -> list[GroupView]:
        if not groups:
            return []
        uids = [r.uid for r, _ in groups]
        since = self._clock() - WINDOW
        counts = (
            await self._outcomes.tool_outcomes(resource_uids=uids, since=since)
            if self._outcomes is not None
            else {}
        )
        out: list[GroupView] = []
        for resource, transport in groups:
            envs = [await self.environment(resource, e) for e in transport.environments]
            enabled = [e for e in envs if e.environment.enabled]
            secret_state = _worst({str(i): e.secret_state for i, e in enumerate(enabled)})
            pending = [a for e in enabled for a in e.pending_approvals]
            pending_secrets = [n for e in enabled for n in e.pending_secrets]
            rejected = [a for e in enabled for a in e.rejected_approvals]
            rejected_secrets = [n for e in enabled for n in e.rejected_secrets]
            last = (
                await self._outcomes.last_tool_call(resource.uid, since=since)
                if self._outcomes is not None
                else None
            )
            per_tool = counts.get(resource.uid, {})
            tools = [
                ToolView(
                    tool=t,
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
                    environments=envs,
                    pending_approvals=pending,
                    pending_secrets=pending_secrets,
                    rejected_approvals=rejected,
                    rejected_secrets=rejected_secrets,
                    calls=sum(c for c, _ in per_tool.values()),
                    failures=sum(f for _, f in per_tool.values()),
                    last_call_at=last.timestamp if last else None,
                    last_call_status=last.status if last else None,
                    last_call_error=last.error_message if last else None,
                    tools=tools,
                )
            )
        out.sort(key=lambda v: (HEALTH_ORDER[v.health], v.resource.name))
        return out


def _names(approvals: list[SecretApproval]) -> list[str]:
    return [standalone_name(a.ref or "") or (a.ref or "") for a in approvals]


def _worst(states: dict[str, SecretState]) -> SecretState:
    """The worst state of several (``none`` when there are none)."""
    for state in ("missing", "rejected", "pending_approval", "present"):
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
    if secret_state == "rejected":
        return "attention", "approval_rejected"
    if secret_state == "pending_approval":
        return "attention", "approval_pending"
    if last_status == "ok":
        return "healthy", None
    return "idle", None


__all__ = [
    "HEALTH_ORDER",
    "EnvironmentView",
    "GroupHealth",
    "GroupView",
    "GroupViewer",
    "SecretState",
    "ToolView",
]
