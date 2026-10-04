"""``/api/v1/daemon/port`` — read and set the port of the next start.

Spec daemon "Bind a fixed, settable port": the running daemon accepts a new
port from Settings → Daemon. The value is checked (1024-65535, held by no other
process — this daemon's own port counts as free) and written to the pre-bind
``daemon-config.json`` exactly as ``coffer config set daemon.port`` writes it;
the daemon keeps answering where it is until it restarts. The CLI stays the
escape hatch for a daemon that cannot bind its port, since no route can answer
then.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.port_setting import pin_port
from coffer.surfaces.http import daemon_port
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.daemon_schemas import DaemonPortIn, DaemonPortOut

router = APIRouter(prefix="/api/v1/daemon", tags=["daemon"], dependencies=[Depends(require_token)])


def _port_out() -> DaemonPortOut:
    configured = daemon_config.effective_port()
    bound = daemon_port.get_port()
    # Pending only when a port was saved and this daemon is not on it. With
    # nothing saved there is nothing to apply: a daemon the test suite started
    # in its port range answers elsewhere than 38470 without anything pending.
    saved = daemon_config.read_fixed_port() is not None
    return DaemonPortOut(port=configured, bound_port=bound, pending=saved and configured != bound)


@router.get("/port", response_model=DaemonPortOut)
async def get_daemon_port() -> DaemonPortOut:
    return await asyncio.to_thread(_port_out)


@router.put("/port", response_model=DaemonPortOut)
async def put_daemon_port(body: DaemonPortIn) -> DaemonPortOut:
    """Save the port of the next start; refused in place when it cannot be bound."""
    bound = daemon_port.get_port()
    # psutil's process walk and the probe bind are blocking.
    await asyncio.to_thread(pin_port, body.port, bound_port=bound)
    return await asyncio.to_thread(_port_out)
