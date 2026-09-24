"""The background passes of a switched-off feature skip their rounds.

Spec experimental-features "Close every surface of a switched-off feature":
converge (``vault_sync``), curation (``knowledge``), aggregation and distil
(``memory``) read the switch at the top of every round. Each pass is started
through its real wiring function with fakes behind it, so what is asserted is
the check the composition root actually installs — and a switch flipped on the
same service reaches the next round without a restart.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from coffer.application.features import FeatureService
from coffer.application.sync.worker import ConvergeWorker
from coffer.surfaces.http import curation_wiring, memory_wiring, sync_wiring


class _Settings:
    def __init__(self, stored: dict[str, bool]) -> None:
        self.stored = dict(stored)

    def read(self) -> dict[str, bool]:
        return dict(self.stored)

    def write(self, key: str, enabled: bool) -> None:
        self.stored[key] = enabled


def _features(**off: bool) -> FeatureService:
    return FeatureService(channel="dev", settings=_Settings(off))


class _EngineConfig:
    """Every upkeep pass switched on, on this machine: only the feature decides."""

    async def get(self) -> Any:
        return SimpleNamespace(
            upkeep=lambda _name: SimpleNamespace(enabled=True, interval_s=None),
            curate_runs_on=lambda _machine: True,
        )


def _capture(monkeypatch: pytest.MonkeyPatch, module: Any, name: str) -> dict[str, Any]:
    """Replace a worker class in its wiring module with one that records the
    arguments it was built with and never loops."""
    seen: dict[str, Any] = {}

    class _Recorder:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            seen.update(kwargs)

        async def run_forever(self) -> None:
            return None

        def start(self) -> None:
            return None

    monkeypatch.setattr(module, name, _Recorder)
    return seen


@pytest.mark.acceptance(
    spec="experimental-features", scenario="a switched-off feature's pass skips its round"
)
async def test_the_aggregation_worker_runs_no_pass_while_memory_is_off() -> None:
    calls: list[str] = []

    async def aggregate(*, actor: str) -> None:
        calls.append(actor)

    features = _features(memory=False)
    service = SimpleNamespace(aggregate=aggregate)
    task = memory_wiring.start_aggregate_worker(
        service,  # type: ignore[arg-type]
        _EngineConfig(),  # type: ignore[arg-type]
        features,
    )
    try:
        # The worker's first round runs at once, on start.
        await asyncio.sleep(0.05)
        assert calls == []

    finally:
        await memory_wiring.stop_aggregate_worker(task)

    # Switched on, the same service's next worker round runs — the control
    # that shows the round above was skipped rather than never due.
    await features.set("memory", True)
    task = memory_wiring.start_aggregate_worker(
        service,  # type: ignore[arg-type]
        _EngineConfig(),  # type: ignore[arg-type]
        features,
    )
    try:
        await asyncio.sleep(0.05)
        assert len(calls) == 1
    finally:
        await memory_wiring.stop_aggregate_worker(task)


async def test_the_distil_worker_skips_while_memory_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _capture(monkeypatch, memory_wiring, "DistilWorker")
    features = _features(memory=False)
    task = memory_wiring.start_distil_worker(
        lambda *_a, **_k: None,  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        _EngineConfig(),  # type: ignore[arg-type]
        features,
    )
    await task
    assert await seen["is_enabled"]() is False
    await features.set("memory", True)
    assert await seen["is_enabled"]() is True


async def test_the_curation_worker_skips_while_knowledge_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _capture(monkeypatch, curation_wiring, "CurationWorker")

    async def no_divergence() -> bool:
        return False

    sync = SimpleNamespace(
        registry=SimpleNamespace(machine_id="m1"),
        service=SimpleNamespace(lock=asyncio.Lock(), divergence_outstanding=no_divergence),
    )
    features = _features(knowledge=False)
    task = curation_wiring.start_curation_worker(
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(refresh=None),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        _EngineConfig(),  # type: ignore[arg-type]
        sync,  # type: ignore[arg-type]
        features,
    )
    await task
    assert await seen["is_enabled"]() is False
    await features.set("knowledge", True)
    assert await seen["is_enabled"]() is True


async def test_the_converge_worker_skips_while_vault_sync_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _capture(monkeypatch, sync_wiring, "ConvergeWorker")
    features = _features(vault_sync=False)
    sync_wiring.start_converge_worker(
        SimpleNamespace(service=SimpleNamespace()),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        features,
    )
    assert seen["is_enabled"]() is False
    await features.set("vault_sync", True)
    assert seen["is_enabled"]() is True


async def test_a_skipped_converge_round_never_reaches_the_service() -> None:
    rounds: list[int] = []

    class _Service:
        async def run_once(self) -> Any:
            rounds.append(1)
            raise RuntimeError("the round ran")

    on = {"value": False}
    worker = ConvergeWorker(
        _Service(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        is_enabled=lambda: on["value"],
    )
    await worker.tick()
    assert rounds == []
    on["value"] = True
    await worker.tick()  # the raise is logged, never propagated
    assert rounds == [1]
