"""The background passes of a switched-off feature skip their rounds.

Spec experimental-features "Close every surface of a switched-off feature":
the sync worker (``sync``), curation (``knowledge``), aggregation and distil
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
from coffer.application.sync.worker import SyncWorker
from coffer.domain.features import feature_keys
from coffer.surfaces.http import curation_wiring, memory_wiring, sync_wiring


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
    spec="experimental-features",
    scenario="memory off skips the distil and aggregate passes",
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


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="knowledge off skips the curation pass",
)
async def test_the_curation_worker_skips_while_knowledge_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _capture(monkeypatch, curation_wiring, "CurationWorker")

    async def no_divergence() -> bool:
        return False

    sync = SimpleNamespace(
        registry=SimpleNamespace(machine_id="m1"),
        service=SimpleNamespace(
            lock=asyncio.Lock(), divergence_outstanding=no_divergence, machine_id="m1"
        ),
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


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="sync off treats the vault as single-machine for curation",
)
@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="sync off leaves the vault single-machine",
)
async def test_curation_treats_the_vault_as_single_machine_while_sync_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With sync closed there is no other machine to fold the same material, so
    an owner id the user cannot reach must not stall curation."""
    seen = _capture(monkeypatch, curation_wiring, "CurationWorker")

    class _OwnedElsewhere:
        async def get(self) -> Any:
            return SimpleNamespace(
                upkeep=lambda _name: SimpleNamespace(enabled=True, interval_s=None),
                curate_runs_on=lambda _machine: False,
            )

    async def held() -> bool:
        return True

    sync = SimpleNamespace(
        registry=SimpleNamespace(machine_id="m1"),
        service=SimpleNamespace(lock=asyncio.Lock(), divergence_outstanding=held, machine_id="m1"),
    )
    features = _features(sync=False)
    task = curation_wiring.start_curation_worker(
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(refresh=None),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        _OwnedElsewhere(),  # type: ignore[arg-type]
        sync,  # type: ignore[arg-type]
        features,
    )
    await task
    assert await seen["is_enabled"]() is True
    await features.set("sync", True)
    assert await seen["is_enabled"]() is False


async def test_the_sync_worker_is_built_with_the_sync_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _capture(monkeypatch, sync_wiring, "SyncWorker")
    features = _features(sync=False)
    sync_wiring.start_sync_worker(
        SimpleNamespace(service=SimpleNamespace()),  # type: ignore[arg-type]
        features,
    )
    assert seen["is_enabled"]() is False
    await features.set("sync", True)
    assert seen["is_enabled"]() is True


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="sync off skips convergence rounds and keeps the remote",
)
async def test_a_skipped_sync_round_never_reaches_the_service() -> None:
    rounds: list[int] = []

    class _Service:
        def remote(self) -> Any:
            return SimpleNamespace(enabled=True, interval_seconds=60)

        def set_next_round(self, _when: Any) -> None:
            return None

        async def run(self, *, trigger: str = "timer") -> Any:
            rounds.append(1)
            raise RuntimeError("the round ran")

    on = {"value": False}
    worker = SyncWorker(_Service(), is_enabled=lambda: on["value"])  # type: ignore[arg-type]
    await worker.tick()
    assert rounds == []
    on["value"] = True
    await worker.tick()  # the raise is logged, never propagated
    assert rounds == [1]


@pytest.mark.acceptance(
    spec="experimental-features", scenario="models off leaves knowledge and memory working"
)
async def test_the_knowledge_passes_do_not_depend_on_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switching ``models`` off closes the connection picker, not the chosen
    connection: the passes read only ``knowledge`` (and their own switches)."""
    seen = _capture(monkeypatch, curation_wiring, "CurationWorker")

    async def no_divergence() -> bool:
        return False

    sync = SimpleNamespace(
        registry=SimpleNamespace(machine_id="m1"),
        service=SimpleNamespace(
            lock=asyncio.Lock(), divergence_outstanding=no_divergence, machine_id="m1"
        ),
    )
    features = _features(models=False)
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
    assert features.is_enabled("models") is False
    assert await seen["is_enabled"]() is True
