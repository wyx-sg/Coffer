"""Hand an operation only a present person may approve to the desktop app.

Spec secret "Approve from the command line with the person's own presence
check"; design align-cli-with-ui-and-add-tool-environments D8. The command
leaves a desktop request with the daemon and waits; the app's shell runs the
operating system's presence check itself. When no shell has polled lately the
app is started (``open -b`` on macOS) and given a moment to come up; where it
cannot be started — no app, not a Mac, a session with no person at it — the
command says so and exits 12, and nothing is approved.

Nothing here touches a key, a grant or a value: the command learns only how
the request ended, and then reads the approvals' real state from the daemon.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from typing import Any

from coffer.infrastructure.platform.desktop import launch_app_command
from coffer.surfaces.cli import _io
from coffer.surfaces.cli._options import ExitCode

#: The app's bundle identifier (``desktop/tauri.conf.json``).
BUNDLE_ID = "dev.coffer.desktop"
#: How long a just-started app has to begin polling.
LAUNCH_WAIT_SECONDS = 30.0
POLL_SECONDS = 0.5
TERMINAL = {"done", "cancelled", "failed", "expired"}


def launch_app() -> bool:
    """Start the desktop app; whether a start was attempted. Tests replace it."""
    argv = launch_app_command(BUNDLE_ID)
    if argv is None:
        return False
    try:
        subprocess.run(argv, check=True, capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


#: Indirection for tests: how to sleep, and how to start the app.
sleep: Callable[[float], None] = time.sleep
launcher: Callable[[], bool] = launch_app


def ensure_shell(*, as_json: bool, launch: bool = True) -> None:
    """Return once a desktop shell is polling, or exit 12."""
    if _io.call("GET", "/desktop/status", as_json=as_json)["shell_running"]:
        return
    if launch and launcher():
        deadline = time.monotonic() + LAUNCH_WAIT_SECONDS
        while time.monotonic() < deadline:
            sleep(POLL_SECONDS)
            if _io.call("GET", "/desktop/status", as_json=as_json)["shell_running"]:
                return
    _io.fail(
        "CLI_APP_UNAVAILABLE",
        "the Coffer desktop app is not running"
        + ("" if launch else " (--no-launch)")
        + "; open it on this Mac and run the command again — nothing was approved",
        ExitCode.APP_UNAVAILABLE,
        as_json=as_json,
    )


def run(
    body: dict[str, Any], *, as_json: bool, timeout: float, launch: bool = True
) -> dict[str, Any]:
    """Create a desktop request, wait for it to end, and return it."""
    ensure_shell(as_json=as_json, launch=launch)
    request = _io.call("POST", "/desktop/requests", as_json=as_json, body=body)
    deadline = time.monotonic() + timeout
    while request["status"] not in TERMINAL:
        if time.monotonic() >= deadline:
            request = _io.call("POST", f"/desktop/requests/{request['id']}/cancel", as_json=as_json)
            if request["status"] not in TERMINAL:
                request = {**request, "status": "expired", "message": "timed out waiting"}
            break
        sleep(POLL_SECONDS)
        request = _io.call("GET", f"/desktop/requests/{request['id']}", as_json=as_json)
    return dict(request)


__all__ = ["BUNDLE_ID", "ensure_shell", "launch_app", "run"]
