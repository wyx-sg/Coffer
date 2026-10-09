"""Wire the daemon's release check (spec daemon "Check the installed binaries
for a new release").

Only a daemon running from the installer's frozen binaries checks: the desktop
app checks its signed manifest itself, and a source checkout is upgraded with
git. The check is one supervised loop; ``tasks().shutdown()`` cancels it.
"""

from __future__ import annotations

import coffer
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.application.upgrade_handoff import InstallMethod
from coffer.infrastructure.daemon.install_method import install_facts
from coffer.infrastructure.daemon.release_check import ReleaseCheck

_check: ReleaseCheck | None = None


def wire_release_check() -> ReleaseCheck:
    """Build the check for this daemon and start its loop when it applies."""
    global _check
    applies = install_facts().method is InstallMethod.BINARIES
    check = ReleaseCheck(running=coffer.__version__, applies=applies)
    _check = check
    if check.checks():
        spawn_restarting(check.run, name="release-check")
    return check


def set_release_check(check: ReleaseCheck | None) -> None:
    """Tests install their own check (or none)."""
    global _check
    _check = check


def get_release_check() -> ReleaseCheck:
    """The daemon's check; before wiring (a bare test app), one that never checks."""
    if _check is None:
        return ReleaseCheck(running=coffer.__version__, applies=False)
    return _check


__all__ = ["get_release_check", "set_release_check", "wire_release_check"]
