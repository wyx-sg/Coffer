"""Machine activation slice (spec 010 amendment — Machines fleet view,
ADR-045).

Given a machine id already confirmed present in the synced machines
registry, computes what's active FOR that machine — from each resource's
machine x agent ``scope`` — so any machine can render any machine's fleet
view. Pure intent: registry + scope math only, no local FS/process checks
(those stay in the existing per-machine endpoints; the frontend Machines
view renders on-machine actuals for the *local* machine from those, not
from this slice).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from coffer.application.resource_service import ResourceService
from coffer.domain.scope import agent_in_scope, machine_in_scope
from coffer.domain.sync.errors import MachineNotFound
from coffer.domain.sync.models import MachineEntry


@dataclass(frozen=True)
class AgentActivation:
    name: str
    active: bool


@dataclass(frozen=True)
class DualAxisActivation:
    """An mcp_server/skill row's activation on one machine, plus which of
    that machine's active agents may use it there (matrix intersected with
    each agent's own machine axis)."""

    name: str
    active: bool
    agents: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChannelActivation:
    name: str
    active: bool


@dataclass(frozen=True)
class MachineSlice:
    agents: list[AgentActivation]
    mcp_servers: list[DualAxisActivation]
    skills: list[DualAxisActivation]
    channels: list[ChannelActivation]


async def compute_slice(
    machine_id: str,
    entries: Sequence[MachineEntry],
    *,
    resources: ResourceService,
) -> MachineSlice:
    """Compute ``machine_id``'s activation slice.

    Raises :class:`MachineNotFound` if ``machine_id`` is not among
    ``entries`` (the caller's already-fetched registry listing, e.g. from
    ``SyncService.list_machines()`` — passed in rather than re-fetched here
    so the route can reuse the same listing to build the ``machine`` field).
    """
    if not any(e.machine_id == machine_id for e in entries):
        raise MachineNotFound(machine_id)

    agent_rows = await resources.list(kind="agent")
    active_agent_names = {
        r.name for r in agent_rows if r.enabled and machine_in_scope(r.scope, machine_id)
    }
    agents = [AgentActivation(name=r.name, active=r.name in active_agent_names) for r in agent_rows]

    async def _dual_axis(kind: str) -> list[DualAxisActivation]:
        rows = await resources.list(kind=kind)
        out: list[DualAxisActivation] = []
        for r in rows:
            active = r.enabled and machine_in_scope(r.scope, machine_id)
            names = (
                sorted(a for a in active_agent_names if agent_in_scope(r.scope, machine_id, a))
                if active
                else []
            )
            out.append(DualAxisActivation(name=r.name, active=active, agents=names))
        return out

    mcp_servers = await _dual_axis("mcp_server")
    skills = await _dual_axis("skill")

    channel_rows = await resources.list(kind="channel")
    channels = [
        ChannelActivation(name=r.name, active=r.enabled and machine_in_scope(r.scope, machine_id))
        for r in channel_rows
    ]

    return MachineSlice(agents=agents, mcp_servers=mcp_servers, skills=skills, channels=channels)
