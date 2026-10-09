"""``/api/v1/daemon/upgrade`` — how Coffer is upgraded on this machine (spec
daemon "Hand an upgrade of Coffer to an agent" and "Check the installed
binaries for a new release").

Settings > About reads it in a browser, where no control can install an
update: the prompt carries the running version, how this copy was installed
(``infrastructure/daemon/install_method.py``) and the machine, and the page
offers it to the person's agent. A daemon running from the installer's
binaries also reports the newest release its own check found
(``infrastructure/daemon/release_check.py``), which ``coffer update`` installs.
"""

from __future__ import annotations

import asyncio
from functools import cache

from fastapi import APIRouter, Depends

import coffer
from coffer.application.upgrade_handoff import upgrade_handoff
from coffer.infrastructure.daemon.install_method import install_facts
from coffer.infrastructure.daemon.release_check import ReleaseCheck, write_check_setting
from coffer.infrastructure.platform.host import machine_label
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.daemon_schemas import DaemonUpgradeOut, ReleaseOut, UpgradeAutoCheckIn
from coffer.surfaces.http.handoff_schemas import HandoffOut
from coffer.surfaces.http.release_check_wiring import get_release_check

router = APIRouter(prefix="/api/v1/daemon", tags=["daemon"], dependencies=[Depends(require_token)])

#: The OS and architecture do not change while the daemon runs.
_machine = cache(machine_label)


async def _out(check: ReleaseCheck) -> DaemonUpgradeOut:
    install = install_facts()
    machine = await asyncio.to_thread(_machine)
    prompt = upgrade_handoff(coffer.__version__, install, machine)
    found = check.available()
    return DaemonUpgradeOut(
        install_method=install.method.value,
        handoff=HandoffOut(prompt=prompt),
        checks=check.checks(),
        auto_check=check.auto_check(),
        checked_at=check.checked_at,
        last_error=check.last_error,
        available=(
            ReleaseOut(
                version=found.version,
                notes=found.notes,
                published_at=found.published_at,
                url=found.url,
            )
            if found is not None
            else None
        ),
    )


@router.get("/upgrade", response_model=DaemonUpgradeOut)
async def get_upgrade(
    check: ReleaseCheck = Depends(get_release_check),  # noqa: B008
) -> DaemonUpgradeOut:
    return await _out(check)


@router.post("/upgrade/check", response_model=DaemonUpgradeOut)
async def check_upgrade(
    check: ReleaseCheck = Depends(get_release_check),  # noqa: B008
) -> DaemonUpgradeOut:
    """Check for a newer release now (a daemon that does not check answers as is)."""
    await check.check_now()
    return await _out(check)


@router.put("/upgrade/auto-check", response_model=DaemonUpgradeOut)
async def set_upgrade_auto_check(
    body: UpgradeAutoCheckIn,
    check: ReleaseCheck = Depends(get_release_check),  # noqa: B008
) -> DaemonUpgradeOut:
    """Switch the daily check on or off; the loop reads it on its next tick."""
    await asyncio.to_thread(write_check_setting, body.enabled)
    return await _out(check)


__all__ = ["router"]
