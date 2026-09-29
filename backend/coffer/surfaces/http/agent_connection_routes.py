"""/api/v1/agents/{uid}/coffer-connection (spec agent-registry "Connect an agent
to Coffer in one action", "Report an agent's Coffer connection part by part",
"Disconnect an agent from Coffer").

GET reports the connection part by part, POST connects (installs every part
that applies now), DELETE disconnects (removes every part Coffer wrote). Each
part records its own audit event, so these routes record none of their own.
Domain errors (ShimNotFound → 422, MalformedDeliveryConfig → 422,
ResourceNotFound → 404) are mapped centrally by surfaces/http/errors.py.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.agent.connection_service import AgentConnectionService, ConnectionStatus
from coffer.surfaces.http.agent_dependencies import get_agent_connection_service
from coffer.surfaces.http.agent_type_path import resolve_agent_path
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token), Depends(resolve_agent_path)],
)


class CofferConnectionPartOut(BaseModel):
    #: ``mcp`` (the gateway entry) or ``memory_hook`` (the memory delivery hook).
    key: str
    installed: bool
    #: What is installed, when it is — the shim or hook command.
    detail: str | None


class CofferConnectionOut(BaseModel):
    state: Literal["connected", "partial", "disconnected"]
    #: The parts that apply to this agent now, in install order.
    parts: list[CofferConnectionPartOut]


def _out(s: ConnectionStatus) -> CofferConnectionOut:
    return CofferConnectionOut(
        state=s.state.value,
        parts=[
            CofferConnectionPartOut(key=p.key, installed=p.installed, detail=p.detail)
            for p in s.parts
        ],
    )


@router.get("/{uid}/coffer-connection", response_model=CofferConnectionOut)
async def connection_status(
    uid: str,
    svc: AgentConnectionService = Depends(get_agent_connection_service),  # noqa: B008
) -> CofferConnectionOut:
    return _out(await svc.status(uid))


@router.post("/{uid}/coffer-connection", response_model=CofferConnectionOut)
async def connect(
    uid: str,
    svc: AgentConnectionService = Depends(get_agent_connection_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> CofferConnectionOut:
    return _out(await svc.connect(uid, actor=actor))


@router.delete("/{uid}/coffer-connection", response_model=CofferConnectionOut)
async def disconnect(
    uid: str,
    svc: AgentConnectionService = Depends(get_agent_connection_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> CofferConnectionOut:
    return _out(await svc.disconnect(uid, actor=actor))
