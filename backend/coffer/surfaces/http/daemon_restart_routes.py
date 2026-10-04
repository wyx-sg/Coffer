"""``POST /api/v1/daemon/restart`` — the daemon restarts itself (spec daemon
"Restart itself on request").

A page in a browser is served by the daemon, so it cannot stop the daemon and
start another the way the desktop shell or ``coffer daemon restart`` does from
outside. This route does both halves from the inside, in the order that keeps it
a true restart: it starts the successor first — which waits for this process to
exit before it binds anything (``infrastructure/daemon/self_restart.py``) —
then answers 202, and only after the answer has gone out takes the ordinary
graceful exit. A successor that cannot be started is a 500 and this daemon keeps
running, so a failed restart never leaves nothing behind.

The answer names the port the successor binds — the pre-bind config's, so a
port saved on Settings → Daemon applies here — for the page to find it on. The
successor mints a new token, as every start does; the page reloads from its
origin to pick it up.
"""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.infrastructure.daemon import bootstrap, self_restart
from coffer.surfaces.http import daemon_port
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.daemon_schemas import DaemonRestartOut
from coffer.surfaces.http.dependencies import get_actor, get_audit_service_optional

router = APIRouter(prefix="/api/v1/daemon", tags=["daemon"], dependencies=[Depends(require_token)])


@dataclass(frozen=True)
class SelfRestart:
    """The two halves, injected so a test never restarts a real daemon."""

    #: Start the detached successor; its pid. Raises ``OSError``.
    spawn_successor: Callable[[], int]
    #: Take the graceful exit (the shutdown signal to this process).
    exit_self: Callable[[], None]


def _exit_gracefully() -> None:
    """The shutdown route's own exit: SIGTERM to this process, which uvicorn
    turns into a graceful shutdown (open connections get their grace)."""
    os.kill(os.getpid(), signal.SIGTERM)


def get_self_restart() -> SelfRestart:
    return SelfRestart(spawn_successor=self_restart.spawn_successor, exit_self=_exit_gracefully)


#: Set as soon as a restart is claimed (before the successor is spawned): a
#: second press while this daemon is on its way out answers the same way
#: instead of starting a second successor.
_RESTARTING = False


def reset_restart_state() -> None:
    """For tests: forget that a restart was asked for."""
    global _RESTARTING
    _RESTARTING = False


@router.post("/restart", status_code=status.HTTP_202_ACCEPTED, response_model=DaemonRestartOut)
async def restart_daemon(
    background: BackgroundTasks,
    restart: SelfRestart = Depends(get_self_restart),  # noqa: B008
    # Optional: a daemon waiting in its setup state wires no audit store, and
    # restarting is how it finishes booting once git is there (spec daemon
    # "Wait in a setup state when git is missing or too old").
    audit: AuditService | None = Depends(get_audit_service_optional),  # noqa: B008
    actor: str = Depends(get_actor),
) -> DaemonRestartOut:
    """Start a successor, then exit once this answer is sent.

    The successor binds the configured port (``port``), or this one when a
    test port range is in force. 500 when the successor cannot be started;
    this daemon then keeps serving.
    """
    global _RESTARTING
    port = bootstrap.planned_port() or daemon_port.get_port()
    if _RESTARTING:
        return DaemonRestartOut(port=port)
    # Claimed before the spawn is awaited: a second request arriving while the
    # first is still spawning must see the claim, not start a second successor.
    _RESTARTING = True
    try:
        successor = await asyncio.to_thread(restart.spawn_successor)
    except OSError as exc:
        _RESTARTING = False
        raise HTTPException(
            status_code=500, detail=f"could not start the replacement daemon: {exc}"
        ) from None
    if audit is not None:
        await audit.record(
            AuditEventType.DAEMON_RESTARTED.value,
            actor=actor,
            details={"port": port, "successor_pid": successor},
        )
    background.add_task(restart.exit_self)
    return DaemonRestartOut(port=port)


__all__ = ["SelfRestart", "get_self_restart", "reset_restart_state", "router"]
