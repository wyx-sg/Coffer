"""File-tree watcher feeding auto-sync change notifications (spec 010).

Watches the live knowledge/memory/skills roots with ``watchfiles`` and calls
``notify`` on every batch of changes. This is the only signal that catches
writes bypassing the daemon (agents edit memory through native symlinks,
ADR-013); daemon-mediated resource mutations notify directly.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Callable, Sequence

import structlog
import watchfiles

_log = structlog.get_logger(__name__)


async def watch_trees(
    roots: Sequence[pathlib.Path],
    notify: Callable[[], None],
    stop_event: asyncio.Event,
) -> None:
    """Run until ``stop_event`` is set; never raises (a watcher crash must not
    take the daemon down — the interval sweep still converges without it)."""
    try:
        for root in roots:
            root.mkdir(parents=True, exist_ok=True)
        async for _changes in watchfiles.awatch(*roots, stop_event=stop_event):
            notify()
    except Exception as e:  # pragma: no cover - platform-specific failures
        _log.warning("sync_watcher_stopped", error=str(e))
