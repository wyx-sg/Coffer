from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)
_DEFAULT_IDLE_DELAY_SECONDS = 300.0  # 5 min idle ≈ session end (conservative)


class OrganizePort(Protocol):
    async def organize(self, *, store_name: str) -> Any: ...


class MemoryAutoOrganizer:
    """Debounced, non-blocking background organize on store idle (FR-035).

    Wired to MemoryService.set_on_change. A single coalescing timer: each write
    (re)arms it; after `delay_seconds` of quiet it organizes the changed store(s)
    as a background task. shutdown() cancels a pending timer WITHOUT firing —
    the un-fired inbox is left intact (recall covers it; organize is idempotent).
    """

    def __init__(
        self,
        *,
        organize: OrganizePort,
        delay_seconds: float = _DEFAULT_IDLE_DELAY_SECONDS,
    ) -> None:
        self._organize = organize
        self._delay = delay_seconds
        self._dirty: set[str] = set()
        self._task: asyncio.Task[None] | None = None

    async def on_change(self, store_name: str) -> None:
        self._dirty.add(store_name)
        if self._task is not None and not self._task.done():
            self._task.cancel()  # re-arm; dirty set is preserved
        self._task = asyncio.create_task(self._run_after_delay())

    async def _run_after_delay(self) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            return  # re-armed or shutting down; a newer timer owns the dirty set
        stores = sorted(self._dirty)
        self._dirty.clear()
        for name in stores:
            try:
                await self._organize.organize(store_name=name)
            except Exception:
                logger.warning(
                    "memory.auto_organize.failed",
                    extra={"store": name},
                    exc_info=True,
                )

    async def shutdown(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
