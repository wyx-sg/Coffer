"""The daemon's setup state: serving, but waiting for git before it opens the
vault (spec daemon "Wait in a setup state when git is missing or too old").

The vault is a git repository, so a daemon on a machine with no git — or one
older than the vault's merges need — cannot open it. It still starts, so the
person learns why instead of meeting "daemon offline": it serves the web UI,
publishes its token and port, and answers ``/daemon/status`` with ``status:
"setup"`` and what it waits for. Nothing that touches the vault is wired
(:mod:`coffer.surfaces.http.setup_lifespan` skips the whole composition), and
this module's middleware refuses every other API route and ``/mcp`` with 503
``GIT_NEEDED``, carrying the same message and hand-off the status reports — so
the CLI and an agent's MCP client say the same thing the page does.

Four routes stay open: the status, Check again (``POST
/daemon/setup/check``), restart and shutdown. Check again looks for git again;
once there is one, the page restarts the daemon (the desktop shell from
outside, a browser through ``/daemon/restart``) and the successor starts
normally. A restart rather than wiring the vault into this process: the
composition root builds every kind in one lifespan whose order is its
dependency order, and the desktop shell's handshake and the page's token both
already follow a restart.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from coffer.domain.git_handoff import GitNeeded, git_setup_details, git_setup_message
from coffer.infrastructure.daemon.phase import get_daemon_phase, set_daemon_phase
from coffer.infrastructure.platform.host import machine_label
from coffer.infrastructure.vault import git_requirement
from coffer.infrastructure.vault.git_requirement import MIN_GIT, GitCheck, use_git_dir, version_text
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.daemon_schemas import DaemonSetupCheckOut, DaemonSetupOut
from coffer.surfaces.http.handoff_schemas import HandoffOut

#: The routes a daemon in its setup state still answers under ``/api/``.
OPEN_PATHS = frozenset(
    {
        "/api/v1/daemon/status",
        "/api/v1/daemon/setup/check",
        "/api/v1/daemon/restart",
        "/api/v1/daemon/shutdown",
    }
)
#: What the setup state refuses: the API, and the MCP endpoint agents call.
_GUARDED_PREFIXES = ("/api/", "/mcp")

_SETUP: DaemonSetupOut | None = None


def setup_of(check: GitCheck) -> DaemonSetupOut:
    """What a failed check reports: the reason, the versions and the hand-off."""
    found = check.found_version
    needed = version_text(MIN_GIT)
    details = git_setup_details(machine_label(), found=found, needed=needed)
    handoff = details["handoff"]
    assert isinstance(handoff, dict)
    return DaemonSetupOut(
        need="git",
        reason="git_missing" if found is None else "git_too_old",
        found=found,
        needed=needed,
        message=git_setup_message(found=found, needed=needed),
        handoff=HandoffOut(prompt=str(handoff["prompt"])),
    )


def current_setup() -> DaemonSetupOut | None:
    """What the daemon waits for, or ``None`` when it is not in its setup state."""
    return _SETUP if get_daemon_phase() == "setup" else None


def enter_setup(check: GitCheck) -> DaemonSetupOut:
    """Put the daemon in its setup state for ``check``'s problem."""
    global _SETUP
    _SETUP = setup_of(check)
    set_daemon_phase("setup")
    return _SETUP


def leave_setup() -> None:
    """For tests: forget the setup state."""
    global _SETUP
    _SETUP = None
    if get_daemon_phase() == "setup":
        set_daemon_phase("ready")


def refusal(setup: DaemonSetupOut) -> GitNeeded:
    """The error every refused route answers with."""
    return GitNeeded(
        setup.message,
        {
            "reason": setup.reason,
            "found": setup.found,
            "needed": setup.needed,
            "handoff": {"prompt": setup.handoff.prompt},
        },
    )


class SetupGuardMiddleware:
    """Raw ASGI, like the host guard: it only reads the path before delegating,
    so it stays out of the SSE streams' way when the daemon is not in setup."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        setup = current_setup() if scope["type"] in ("http", "websocket") else None
        path = scope.get("path", "")
        if setup is None or path in OPEN_PATHS or not path.startswith(_GUARDED_PREFIXES):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1013})  # try again later
            return
        error = refusal(setup)
        response = JSONResponse(
            status_code=503,
            content={
                "error": {"code": error.code, "message": str(error), "details": error.error_details}
            },
        )
        await response(scope, receive, send)


def install(app: FastAPI) -> None:
    app.add_middleware(SetupGuardMiddleware)


router = APIRouter(prefix="/api/v1/daemon", tags=["daemon"], dependencies=[Depends(require_token)])


@router.post("/setup/check", response_model=DaemonSetupCheckOut)
async def check_again() -> DaemonSetupCheckOut:
    """Look for git again, on the daemon's ``PATH`` and the login shell's.

    ``ready`` once a usable git is there; a git found only on the login
    shell's ``PATH`` is put first on this process's, so the restart that
    follows — which inherits this environment — runs it too. A daemon that is
    not in its setup state is ready already.
    """
    if current_setup() is None:
        return DaemonSetupCheckOut(ready=True)
    check = await asyncio.to_thread(git_requirement.check_git)
    if check.ok:
        use_git_dir(check)
        return DaemonSetupCheckOut(ready=True)
    return DaemonSetupCheckOut(ready=False, setup=enter_setup(check))


__all__ = [
    "OPEN_PATHS",
    "SetupGuardMiddleware",
    "current_setup",
    "enter_setup",
    "install",
    "leave_setup",
    "refusal",
    "router",
    "setup_of",
]
