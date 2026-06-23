"""Bounded async worker pool for non-blocking operations.

Drains an ``asyncio.Queue`` of work items with a fixed concurrency cap so a batch
(e.g. distilling hundreds of transcripts, each a live LLM call) cannot saturate
the internal engine. ``enqueue`` records the item as queued and returns
immediately; a worker marks it running, invokes the supplied coroutine factory,
clears the registry entry on success, or records the error on failure.

Follows the codebase's worker-loop shape (see ``retention_worker``): exceptions
in a work item are logged and recorded but never kill a worker.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from coffer.application.async_ops.registry import AsyncOpRegistry

_logger = logging.getLogger(__name__)

# A factory that, when called, returns the awaitable doing the actual work.
WorkFactory = Callable[[], Awaitable[None]]


class AsyncOpRunner:
    """A fixed pool of workers draining a shared queue of async work items."""

    def __init__(self, registry: AsyncOpRegistry, *, concurrency: int = 2) -> None:
        self._registry = registry
        self._concurrency = max(1, concurrency)
        self._queue: asyncio.Queue[tuple[str, str, WorkFactory]] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        """Spawn the worker tasks (idempotent)."""
        if self._workers:
            return
        self._workers = [
            asyncio.create_task(self._worker_loop(), name=f"async-op-worker-{i}")
            for i in range(self._concurrency)
        ]

    async def stop(self) -> None:
        """Cancel and await all workers (in-flight items drop to their derived status)."""
        for task in self._workers:
            task.cancel()
        for task in self._workers:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._workers = []

    def enqueue(self, op_type: str, item_key: str, factory: WorkFactory) -> None:
        """Record the item as queued and hand it to a worker. Returns immediately."""
        self._registry.mark_queued(op_type, item_key)
        self._queue.put_nowait((op_type, item_key, factory))

    async def _worker_loop(self) -> None:
        while True:
            op_type, item_key, factory = await self._queue.get()
            self._registry.mark_running(op_type, item_key)
            try:
                await factory()
                self._registry.clear(op_type, item_key)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _logger.exception(
                    "async_op.failed",
                    extra={"op_type": op_type, "item_key": item_key},
                )
                self._registry.mark_error(op_type, item_key, str(exc))
            finally:
                self._queue.task_done()
