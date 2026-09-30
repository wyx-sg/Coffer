"""Keep the daemon's own background repair out of a test that plants drift.

A test that removes a link and then asks ``verify`` (or the drift plan) to
report it races the reconciler: the pass a preceding write hinted runs after a
short settle and repairs the link first, so on a loaded machine the report can
come back clean. Such a test is about the command, not the background loop,
so it switches hint-triggered passes off before planting the drift and waits
out any pass already in flight.
"""

from __future__ import annotations

import time

import pytest

from coffer.surfaces.http.reconcile_dependencies import get_reconciler


def quiet_background_repair(monkeypatch: pytest.MonkeyPatch, *, timeout: float = 10.0) -> None:
    """Stop new hint-triggered passes, then wait until none is pending or running."""
    reconciler = get_reconciler()
    monkeypatch.setattr(reconciler, "hint", lambda changed: None)
    deadline = time.monotonic() + timeout
    quiet_since: float | None = None
    while time.monotonic() < deadline:
        busy = bool(reconciler.pending_hints) or reconciler._lock.locked()
        if busy:
            quiet_since = None
        elif quiet_since is None:
            quiet_since = time.monotonic()
        elif time.monotonic() - quiet_since > 1.0:
            return
        time.sleep(0.05)
    raise AssertionError("the reconciler did not go quiet")
