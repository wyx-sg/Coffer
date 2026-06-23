"""Async batch native-memory import — runs the FR-041 adoption off the request path.

Wraps :meth:`AgentMemoryImportService.import_store` with the shared
:class:`AsyncOpRunner` so the agent Memory tab can fire single / bulk / select-all
imports without blocking and poll per-store status. Each native-memory store is
keyed by its ``memory_dir`` (the store's real identity), scoped per agent via a
``f"{agent}\\x00{memory_dir}"`` registry key. The actual fact-write +
organize-schedule work stays in the existing import service; this module only
enqueues and reports in-flight state.

All collaborators are injected as plain callables so this application module
imports nothing from infrastructure or surfaces.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coffer.application.async_ops.registry import AsyncOpRegistry, InflightEntry, OpState
from coffer.application.async_ops.runner import AsyncOpRunner

#: Operation type key in the shared registry.
OP_TYPE = "native_import"
_SEP = "\x00"  # agent / memory_dir separator in registry keys (neither contains NUL)


@dataclass(frozen=True)
class EnqueueResult:
    """Outcome of a batch import enqueue."""

    queued: int  # newly enqueued stores
    total: int  # candidate stores considered


class NativeImportBatchService:
    """Enqueues native-memory import work and reports per-store status."""

    def __init__(
        self,
        *,
        runner: AsyncOpRunner,
        registry: AsyncOpRegistry,
        import_store: Callable[[str, str], Awaitable[None]],
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._import_store = import_store

    @staticmethod
    def _key(agent: str, memory_dir: str) -> str:
        return f"{agent}{_SEP}{memory_dir}"

    def inflight(self, agent: str) -> dict[str, InflightEntry]:
        """In-flight entries for *agent*, keyed by memory_dir."""
        prefix = f"{agent}{_SEP}"
        snap = self._registry.snapshot(OP_TYPE, prefix=prefix)
        return {key[len(prefix) :]: entry for key, entry in snap.items()}

    def enqueue_import(self, agent: str, memory_dir: str) -> bool:
        """Enqueue a single store; returns whether it was newly enqueued."""
        key = self._key(agent, memory_dir)
        existing = self._registry.get(OP_TYPE, key)
        if existing is not None and existing.state in (OpState.queued, OpState.running):
            return False  # already in flight — don't double-enqueue
        self._runner.enqueue(OP_TYPE, key, self._factory(agent, memory_dir))
        return True

    def enqueue_imports(self, agent: str, memory_dirs: list[str]) -> EnqueueResult:
        """Enqueue an explicit set of stores (skip ones already in flight)."""
        queued = 0
        for memory_dir in memory_dirs:
            if self.enqueue_import(agent, memory_dir):
                queued += 1
        return EnqueueResult(queued=queued, total=len(memory_dirs))

    def _factory(self, agent: str, memory_dir: str) -> Callable[[], Awaitable[None]]:
        async def _run() -> None:
            await self._import_store(agent, memory_dir)

        return _run


__all__ = ["OP_TYPE", "EnqueueResult", "NativeImportBatchService"]
