"""The background passes of a switched-off feature skip their rounds.

Spec experimental-features "Close every surface of a switched-off feature":
the memory sync (``memory``) and the knowledge sweep (``knowledge``)
read the switch at the top of every round; the sync worker, graduated, reads
none. Each pass is started through its real wiring
function with fakes behind it, so what is asserted is the check the
composition root actually installs — and a switch flipped on the same service
reaches the next round without a restart.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from coffer.application.features import FeatureService
from coffer.application.sync.worker import SyncWorker
from coffer.domain.features import feature_keys
from coffer.surfaces.http import knowledge_sweep_wiring, memory_sync_wiring


class _Settings:
    def __init__(self, stored: dict[str, bool]) -> None:
        self.stored = dict(stored)

    def read(self) -> dict[str, bool]:
        return dict(self.stored)

    def write(self, key: str, enabled: bool) -> None:
        self.stored[key] = enabled

    def clear(self, key: str) -> None:
        self.stored.pop(key, None)


def _features(**off: bool) -> FeatureService:
    """Every feature on, except the ones named: those are off."""
    return FeatureService(settings=_Settings(dict.fromkeys(feature_keys(), True) | off))


class _EngineConfig:
    """Every upkeep pass switched on, on this machine: only the feature decides."""

    async def get(self) -> Any:
        return SimpleNamespace(
            upkeep=lambda _name: SimpleNamespace(enabled=True, interval_s=None),
        )


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="memory off skips the memory sync",
)
async def test_the_memory_sync_worker_runs_no_pass_while_memory_is_off() -> None:
    calls: list[str] = []

    async def sync(actor: str) -> None:
        calls.append(actor)

    features = _features(memory=False)
    service = SimpleNamespace(sync=sync)
    task = memory_sync_wiring.start_memory_sync_worker(
        service,  # type: ignore[arg-type]
        _EngineConfig(),  # type: ignore[arg-type]
        features,
    )
    try:
        # The worker's first round runs at once, on start.
        await asyncio.sleep(0.05)
        assert calls == []

    finally:
        await memory_sync_wiring.stop_memory_sync_worker(task)

    # Switched on, the same service's next worker round runs — the control
    # that shows the round above was skipped rather than never due.
    await features.set("memory", True)
    task = memory_sync_wiring.start_memory_sync_worker(
        service,  # type: ignore[arg-type]
        _EngineConfig(),  # type: ignore[arg-type]
        features,
    )
    try:
        await asyncio.sleep(0.05)
        assert len(calls) == 1
    finally:
        await memory_sync_wiring.stop_memory_sync_worker(task)


async def test_a_sync_round_always_reaches_the_service() -> None:
    """Vault sync graduated: the worker has no switch to read, so every round
    with a remote configured reaches the service."""
    rounds: list[int] = []

    class _Service:
        def remote(self) -> Any:
            return SimpleNamespace(enabled=True, interval_seconds=60)

        def set_next_round(self, _when: Any) -> None:
            return None

        async def run(self, *, trigger: str = "timer") -> Any:
            rounds.append(1)
            raise RuntimeError("the round ran")

    worker = SyncWorker(_Service())
    await worker.tick()  # the raise is logged, never propagated
    assert rounds == [1]


def _fake_sweep(monkeypatch: pytest.MonkeyPatch, swept: list[object]) -> None:
    async def record(service: object, _refresh: object) -> None:
        swept.append(service)

    monkeypatch.setattr(knowledge_sweep_wiring, "sweep_once", record)

    class _Tidies:
        async def expire(self) -> list[str]:
            return []

    monkeypatch.setattr(knowledge_sweep_wiring, "get_tidy_service", _Tidies)


async def _sweep_ticks(monkeypatch: pytest.MonkeyPatch, features: FeatureService) -> list[object]:
    """Run the real sweep loop for a few fallbacks; answer what each run swept."""
    swept: list[object] = []
    _fake_sweep(monkeypatch, swept)
    sweep = knowledge_sweep_wiring.KnowledgeSweep(
        "service",  # type: ignore[arg-type]
        SimpleNamespace(refresh=None),  # type: ignore[arg-type]
        features,
        fallback=0.01,
        settle=0.0,
    )
    task = asyncio.create_task(sweep.run())
    try:
        await asyncio.sleep(0.1)
    finally:
        await knowledge_sweep_wiring.stop_knowledge_sweep(task)
    return swept


@pytest.mark.acceptance(
    spec="daemon", scenario="a change under the knowledge area brings the sweep forward"
)
async def test_a_knowledge_file_event_wakes_the_sweep_and_it_is_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coffer.application.runtime.workers import WorkerMode, workers

    swept: list[object] = []
    _fake_sweep(monkeypatch, swept)
    hints: list[Any] = []
    task = knowledge_sweep_wiring.start_knowledge_sweep(
        "service",  # type: ignore[arg-type]
        SimpleNamespace(refresh=None),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        _features(),
        hints.append,
    )
    try:
        await asyncio.sleep(0.2)
        assert len(swept) == 1, "the start-up sweep, and nothing else on a 10 minute fallback"
        row = next(w for w in workers().snapshot() if w.name == "knowledge-sweep")
        assert row.mode == WorkerMode.EVENT_FALLBACK
        (hint,) = hints
        hint()
        hint()  # a burst is one run
        await asyncio.sleep(1.5)
        assert len(swept) == 2
    finally:
        await knowledge_sweep_wiring.stop_knowledge_sweep(task)


@pytest.mark.acceptance(
    spec="experimental-features", scenario="knowledge off skips the knowledge sweep"
)
@pytest.mark.acceptance(
    spec="knowledge", scenario="a switched-off knowledge feature skips the sweep"
)
async def test_the_knowledge_sweep_runs_no_round_while_knowledge_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await _sweep_ticks(monkeypatch, _features(knowledge=False)) == []
    # The control: the same loop, switched on, does sweep.
    assert await _sweep_ticks(monkeypatch, _features()) != []
