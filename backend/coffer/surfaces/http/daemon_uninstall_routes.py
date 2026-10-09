"""``POST /api/v1/daemon/uninstall`` — remove Coffer from this machine (spec
daemon "Uninstall Coffer from this machine").

The daemon owns every write Coffer made outside ``~/.coffer``, so it takes them
out (``application/uninstall.py``), answers with one row per step, and then
stops through the one graceful exit path. Deleting the data needs a presence
grant the desktop app signed for ``uninstall`` over ``delete-data``, redeemed
before anything changes; the purge itself runs in the daemon's exit path once
nothing serves (``infrastructure/daemon/data_purge.py``). The command line
never asks for it here: ``coffer uninstall --delete-data`` purges in its own
process after a confirmation typed at a terminal.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.uninstall import FileStep, MachineSteps, UninstallService
from coffer.infrastructure.daemon import data_purge, uninstall_files
from coffer.surfaces.http.agent_dependencies import (
    get_agent_connection_service,
    get_agent_service,
)
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.daemon_routes import _schedule_shutdown
from coffer.surfaces.http.daemon_schemas import UninstallIn, UninstallOut, UninstallStepOut
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.provider_dependencies import get_provider_service
from coffer.surfaces.http.reconcile_dependencies import get_reconciler
from coffer.surfaces.http.secret_boundary_wiring import get_presence_grants
from coffer.surfaces.http.skill_dependencies import get_skill_service

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/daemon", tags=["daemon"], dependencies=[Depends(require_token)])

#: The target a delete-data grant is signed over.
DELETE_DATA_TARGET = "delete-data"
#: Long enough for the answer to leave before the daemon starts to stop.
_STOP_DELAY_SECONDS = 0.3


def machine_steps() -> MachineSteps:
    return MachineSteps(
        login_job=uninstall_files.remove_login_job,
        terminal_files=uninstall_files.remove_terminal_files,
        path_lines=uninstall_files.remove_path_lines,
        binaries=uninstall_files.remove_binaries,
    )


async def _blocking(step: FileStep) -> Sequence[str]:
    return await asyncio.to_thread(step)


def _optional_provider_service() -> Any:
    try:
        return get_provider_service()
    except RuntimeError:
        return None


@router.post("/uninstall", response_model=UninstallOut)
async def uninstall(
    body: UninstallIn,
    actor: str = Depends(get_actor),
    agents: Any = Depends(get_agent_service),  # noqa: B008
    connections: Any = Depends(get_agent_connection_service),  # noqa: B008
    skills: Any = Depends(get_skill_service),  # noqa: B008
    reconciler: Reconciler = Depends(get_reconciler),  # noqa: B008
) -> UninstallOut:
    if body.delete_data:
        if not body.nonce or not body.signature:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="deleting the data needs a presence grant from the Coffer app",
            )
        get_presence_grants().redeem("uninstall", DELETE_DATA_TARGET, body.nonce, body.signature)
    service = UninstallService(
        agents=agents,
        providers=_optional_provider_service(),
        connections=connections,
        skills=skills,
        reconciler=reconciler,
        machine=machine_steps(),
        run_blocking=_blocking,
    )
    report = await service.run(actor=actor)
    if body.delete_data:
        data_purge.purge_on_exit()
    asyncio.get_running_loop().call_later(_STOP_DELAY_SECONDS, _schedule_shutdown)
    return UninstallOut(
        ok=report.ok,
        steps=[
            UninstallStepOut(key=s.key, outcome=s.outcome, detail=s.detail) for s in report.steps
        ],
        deletes_data=body.delete_data,
    )


__all__ = ["DELETE_DATA_TARGET", "router"]
