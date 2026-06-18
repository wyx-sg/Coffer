"""Instructions-delivery routes (spec 004 item 1).

Two surfaces:

- ``/api/v1/instructions`` — the single hub **master** document (GET/PUT). A PUT
  may carry ``expected_fingerprint`` for optimistic concurrency (409 on stale).
- ``/api/v1/agents/{name}/instructions`` — per-agent delivery: status (GET),
  deliver (POST), remove (DELETE), and adopt (POST ``/adopt``).

Domain errors (InstructionsUnsupported → 422, InstructionsMasterStale → 409,
ResourceNotFound → 404) are mapped centrally by ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.agent.instructions_service import AgentInstructionsService
from coffer.domain.agent.instructions import InstructionsDeliveryStatus, MasterInstructions
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor

# The DI accessor is co-located here rather than in the shared dependencies.py
# (which is at its file-size limit). The composition root calls
# set_agent_instructions_service once on startup.
_service: AgentInstructionsService | None = None


def set_agent_instructions_service(svc: AgentInstructionsService) -> None:
    """Called by the composition root once on startup."""
    global _service
    _service = svc


def get_agent_instructions_service() -> AgentInstructionsService:
    """FastAPI Depends() target."""
    if _service is None:
        raise RuntimeError("agent instructions service not initialised")
    return _service


master_router = APIRouter(
    prefix="/api/v1/instructions",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)

agent_instructions_router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


class MasterInstructionsOut(BaseModel):
    content: str
    fingerprint: str


class MasterInstructionsWrite(BaseModel):
    content: str
    expected_fingerprint: str | None = None


class InstructionsStatusOut(BaseModel):
    delivered: bool
    in_sync: bool


def _master_out(m: MasterInstructions) -> MasterInstructionsOut:
    return MasterInstructionsOut(content=m.content, fingerprint=m.fingerprint)


def _status_out(s: InstructionsDeliveryStatus) -> InstructionsStatusOut:
    return InstructionsStatusOut(delivered=s.delivered, in_sync=s.in_sync)


@master_router.get("", response_model=MasterInstructionsOut)
async def read_master(
    svc: AgentInstructionsService = Depends(get_agent_instructions_service),  # noqa: B008
) -> MasterInstructionsOut:
    return _master_out(svc.get_master())


@master_router.put("", response_model=MasterInstructionsOut)
async def write_master(
    body: MasterInstructionsWrite,
    svc: AgentInstructionsService = Depends(get_agent_instructions_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> MasterInstructionsOut:
    return _master_out(
        await svc.set_master(
            body.content, expected_fingerprint=body.expected_fingerprint, actor=actor
        )
    )


@agent_instructions_router.get("/{name}/instructions", response_model=InstructionsStatusOut)
async def instructions_status(
    name: str,
    svc: AgentInstructionsService = Depends(get_agent_instructions_service),  # noqa: B008
) -> InstructionsStatusOut:
    return _status_out(await svc.status(name))


@agent_instructions_router.post("/{name}/instructions", response_model=InstructionsStatusOut)
async def deliver_instructions(
    name: str,
    svc: AgentInstructionsService = Depends(get_agent_instructions_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> InstructionsStatusOut:
    return _status_out(await svc.deliver(name, actor=actor))


@agent_instructions_router.delete("/{name}/instructions", response_model=InstructionsStatusOut)
async def remove_instructions(
    name: str,
    svc: AgentInstructionsService = Depends(get_agent_instructions_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> InstructionsStatusOut:
    return _status_out(await svc.remove(name, actor=actor))


@agent_instructions_router.post("/{name}/instructions/adopt", response_model=MasterInstructionsOut)
async def adopt_instructions(
    name: str,
    svc: AgentInstructionsService = Depends(get_agent_instructions_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> MasterInstructionsOut:
    return _master_out(await svc.adopt(name, actor=actor))
