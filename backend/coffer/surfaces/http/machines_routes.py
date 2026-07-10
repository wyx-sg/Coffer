"""/api/v1/machines — the Machines fleet view (spec 010 amendment, ADR-045).

``GET /api/v1/machines`` is the same registry as ``GET /api/v1/sync/machines``
(byte-identical wire shape — both build on ``sync_routes.machines_out``), just
surfaced under its own top-level path since the frontend Machines nav item is
not really "sync configuration". ``GET /api/v1/machines/{id}/slice`` renders
that machine's activation slice, computed locally from the synced registry
plus each resource's machine x agent ``scope`` (``application.sync.slice``) —
intent only, no local FS/process checks (those stay in existing per-machine
endpoints).

Depends on ``sync_routes`` for the ``SyncService`` provider (``get_sync_service``)
and the shared ``MachineOut``/``MachinesOut`` models — imported from there
rather than the reverse, so ``sync_routes`` (which this module already needs)
never has to import back into ``machines_routes`` and create a cycle.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.resource_service import ResourceService
from coffer.application.sync.slice import compute_slice
from coffer.domain.sync.errors import MachineNotFound
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.sync_routes import (
    MachineOut,
    MachinesOut,
    get_sync_service,
    machine_out,
    machines_out,
)

router = APIRouter(
    prefix="/api/v1/machines", tags=["machines"], dependencies=[Depends(require_token)]
)


# --- schemas -----------------------------------------------------------


class AgentSliceOut(BaseModel):
    name: str
    active: bool


class DualAxisSliceOut(BaseModel):
    name: str
    active: bool
    agents: list[str]


class ChannelSliceOut(BaseModel):
    name: str
    active: bool


class MachineSliceOut(BaseModel):
    machine: MachineOut
    agents: list[AgentSliceOut]
    mcp_servers: list[DualAxisSliceOut]
    skills: list[DualAxisSliceOut]
    channels: list[ChannelSliceOut]


# --- routes --------------------------------------------------------------


@router.get("", response_model=MachinesOut)
async def list_machines() -> MachinesOut:
    identity, entries = await get_sync_service().list_machines()
    return machines_out(identity, entries)


@router.get("/{machine_id}/slice", response_model=MachineSliceOut)
async def get_machine_slice(
    machine_id: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> MachineSliceOut:
    identity, entries = await get_sync_service().list_machines()
    slice_ = await compute_slice(machine_id, entries, resources=resources)
    # compute_slice already raised MachineNotFound above if machine_id is
    # unknown, so the lookup below is safe.
    entry = next((e for e in entries if e.machine_id == machine_id), None)
    if entry is None:  # pragma: no cover - defence in depth, compute_slice guards this
        raise MachineNotFound(machine_id)
    return MachineSliceOut(
        machine=machine_out(entry, identity),
        agents=[AgentSliceOut(name=a.name, active=a.active) for a in slice_.agents],
        mcp_servers=[
            DualAxisSliceOut(name=m.name, active=m.active, agents=m.agents)
            for m in slice_.mcp_servers
        ],
        skills=[
            DualAxisSliceOut(name=s.name, active=s.active, agents=s.agents) for s in slice_.skills
        ],
        channels=[ChannelSliceOut(name=c.name, active=c.active) for c in slice_.channels],
    )
