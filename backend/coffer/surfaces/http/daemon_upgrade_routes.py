"""``GET /api/v1/daemon/upgrade`` — the hand-off that upgrades Coffer (spec
daemon "Hand an upgrade of Coffer to an agent").

Settings > About reads it in a browser, where no control can install an
update: the prompt carries the running version, how this copy was installed
(``infrastructure/daemon/install_method.py``) and the machine, and the page
offers it to the person's agent.
"""

from __future__ import annotations

import asyncio
from functools import cache

from fastapi import APIRouter, Depends

import coffer
from coffer.application.features import FeatureService
from coffer.application.upgrade_handoff import upgrade_handoff
from coffer.infrastructure.daemon.install_method import install_facts
from coffer.infrastructure.platform.host import machine_label
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.daemon_schemas import DaemonUpgradeOut
from coffer.surfaces.http.feature_dependencies import (
    build_feature_service,
    get_feature_service_optional,
)
from coffer.surfaces.http.handoff_schemas import HandoffOut

router = APIRouter(prefix="/api/v1/daemon", tags=["daemon"], dependencies=[Depends(require_token)])

#: The OS and architecture do not change while the daemon runs.
_machine = cache(machine_label)


@router.get("/upgrade", response_model=DaemonUpgradeOut)
async def get_upgrade(
    features: FeatureService | None = Depends(get_feature_service_optional),  # noqa: B008
) -> DaemonUpgradeOut:
    channel = (features or build_feature_service()).channel
    install = install_facts()
    machine = await asyncio.to_thread(_machine)
    prompt = upgrade_handoff(coffer.__version__, channel, install, machine)
    return DaemonUpgradeOut(install_method=install.method.value, handoff=HandoffOut(prompt=prompt))


__all__ = ["router"]
