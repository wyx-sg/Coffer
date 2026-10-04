"""The daemon's lifecycle phase, shared by the entry and ``/daemon/status``.

It lives in infrastructure because the one place that knows shutdown has begun
is the uvicorn server the entry owns, which runs before the app's lifespan
shutdown and must not import a surface. ``/daemon/status`` reads it.

uvicorn serves only after the lifespan's startup half returns, so no request can
observe the daemon before it is ready: there is no "starting" phase. ``setup``
is a daemon that serves but has not opened the vault, because this machine's
git is missing or too old (spec daemon "Wait in a setup state when git is
missing or too old").
"""

from __future__ import annotations

from typing import Literal

DaemonPhase = Literal["ready", "draining", "setup"]

_PHASE: DaemonPhase = "ready"


def get_daemon_phase() -> DaemonPhase:
    return _PHASE


def set_daemon_phase(phase: DaemonPhase) -> None:
    global _PHASE
    _PHASE = phase
