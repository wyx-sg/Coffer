"""Unit tests for NativeImportBatchService — enqueue logic, in-flight, status."""

from __future__ import annotations

import pytest

from coffer.application.agent.native_import_batch import (
    OP_TYPE,
    NativeImportBatchService,
)
from coffer.application.async_ops.registry import AsyncOpRegistry, OpState
from coffer.application.async_ops.runner import AsyncOpRunner

pytestmark = pytest.mark.asyncio


class _Fixture:
    """A NativeImportBatchService wired against in-memory fakes."""

    def __init__(self) -> None:
        self.registry = AsyncOpRegistry()
        self.runner = AsyncOpRunner(self.registry, concurrency=1)  # not started: enqueue-only
        self.import_calls: list[tuple[str, str]] = []

        async def import_store(agent: str, memory_dir: str) -> None:
            self.import_calls.append((agent, memory_dir))

        self.svc = NativeImportBatchService(
            runner=self.runner,
            registry=self.registry,
            import_store=import_store,
        )


async def test_enqueue_imports_enqueues_every_dir() -> None:
    fx = _Fixture()
    result = fx.svc.enqueue_imports("agent1", ["/a", "/b", "/c"])
    assert result.queued == 3
    assert result.total == 3
    assert fx.registry.get(OP_TYPE, "agent1\x00/a").state is OpState.queued  # type: ignore[union-attr]


async def test_enqueue_import_does_not_double_enqueue_in_flight() -> None:
    fx = _Fixture()
    first = fx.svc.enqueue_import("agent1", "/a")
    second = fx.svc.enqueue_import("agent1", "/a")
    assert first is True
    assert second is False  # already queued — not re-enqueued


async def test_enqueue_imports_skips_in_flight() -> None:
    fx = _Fixture()
    fx.svc.enqueue_import("agent1", "/a")
    result = fx.svc.enqueue_imports("agent1", ["/a", "/b"])
    assert result.queued == 1  # only /b
    assert result.total == 2


async def test_inflight_maps_memory_dir_and_scopes_per_agent() -> None:
    fx = _Fixture()
    fx.svc.enqueue_imports("agent1", ["/a", "/b"])
    fx.svc.enqueue_import("agent2", "/c")
    inflight = fx.svc.inflight("agent1")
    assert set(inflight) == {"/a", "/b"}
    assert inflight["/a"].state is OpState.queued
    assert set(fx.svc.inflight("agent2")) == {"/c"}


async def test_worker_runs_import_and_clears_entry() -> None:
    fx = _Fixture()
    await fx.runner.start()
    try:
        fx.svc.enqueue_import("agent1", "/a")
        await fx.runner._queue.join()  # type: ignore[attr-defined]
    finally:
        await fx.runner.stop()
    assert fx.import_calls == [("agent1", "/a")]
    assert fx.registry.get(OP_TYPE, "agent1\x00/a") is None  # cleared on success
