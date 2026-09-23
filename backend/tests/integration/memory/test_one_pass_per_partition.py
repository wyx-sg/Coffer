"""One distil pass per partition, whoever started it.

See "Run one distil pass per partition at a time".

The timer and the Distil button are two writers over one directory, so both
claim the same upkeep-runs key. The two callers want different things from a
busy partition and get them from the same table: a surface **refuses** with
``UpkeepAlreadyRunning`` (which the HTTP layer answers as
``UPKEEP_ALREADY_RUNNING``, 409) rather than queueing, and the worker
**skips** and comes back on the next sweep.

The HTTP half of that scenario — the status code and the runs surface — is
covered where the route lives. This file covers the half that is this layer's:
which partitions are readable as running, that a worker skips a claimed one,
and that the key is released even when the pass raises, so a crashed pass
cannot wedge a partition for the life of the daemon.
"""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.memory.distil_worker import DistilWorker
from coffer.application.memory.service import KIND_MEMORY
from coffer.application.upkeep_runs import UpkeepRunRegistry
from coffer.domain.errors import UpkeepAlreadyRunning


@pytest.fixture
def runs() -> UpkeepRunRegistry:
    """A registry of this test's own: the production one is a daemon-wide
    singleton, which is right there and wrong here."""
    return UpkeepRunRegistry()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="a second distil pass over the same partition is refused while the first is running",
)
async def test_a_partition_already_being_distilled_is_skipped_by_the_worker(
    runs: UpkeepRunRegistry,
) -> None:
    distilled: list[str] = []

    async def _distil(partition: str) -> None:
        distilled.append(partition)

    async def _partitions() -> list[str]:
        return ["coffer", "global"]

    assert runs.claim(KIND_MEMORY, "coffer") is True  # a pass is in flight by hand

    await DistilWorker(
        distil=_distil, list_partitions=_partitions, start_delay_s=0, runs=runs
    ).run_once()

    assert distilled == ["global"]  # busy is an ordinary state, not a failure


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="a second distil pass over the same partition is refused while the first is running",
)
async def test_a_second_request_over_one_partition_is_refused_rather_than_queued(
    runs: UpkeepRunRegistry,
) -> None:
    with runs.guard(KIND_MEMORY, "coffer"):
        with pytest.raises(UpkeepAlreadyRunning), runs.guard(KIND_MEMORY, "coffer"):
            pass
        # A different partition is unaffected — the key is per target.
        with runs.guard(KIND_MEMORY, "global"):
            pass


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="a second distil pass over the same partition is refused while the first is running",
)
async def test_the_in_flight_pass_is_readable_and_the_list_empties_afterwards(
    runs: UpkeepRunRegistry,
) -> None:
    started = asyncio.Event()
    finish = asyncio.Event()

    async def _distil(partition: str) -> None:
        started.set()
        await finish.wait()

    async def _partitions() -> list[str]:
        return ["coffer"]

    sweep = asyncio.create_task(
        DistilWorker(
            distil=_distil, list_partitions=_partitions, start_delay_s=0, runs=runs
        ).run_once()
    )
    await asyncio.wait_for(started.wait(), timeout=2)

    in_flight = runs.list_running()
    assert [(r.kind, r.name) for r in in_flight] == [(KIND_MEMORY, "coffer")]
    with pytest.raises(UpkeepAlreadyRunning), runs.guard(KIND_MEMORY, "coffer"):
        pass

    finish.set()
    await asyncio.wait_for(sweep, timeout=2)

    assert runs.list_running() == []
    with runs.guard(KIND_MEMORY, "coffer"):  # the next request runs
        pass


@pytest.mark.asyncio
async def test_a_pass_that_raises_still_gives_the_key_back(runs: UpkeepRunRegistry) -> None:
    """A claim that outlived the pass holding it would wedge the partition
    with no runner left to release it."""

    async def _distil(partition: str) -> None:
        raise RuntimeError("the provider is down")

    async def _partitions() -> list[str]:
        return ["coffer"]

    await DistilWorker(
        distil=_distil, list_partitions=_partitions, start_delay_s=0, runs=runs
    ).run_once()

    assert runs.running(KIND_MEMORY, "coffer") is None


@pytest.mark.asyncio
async def test_one_partition_failing_does_not_skip_the_rest(runs: UpkeepRunRegistry) -> None:
    seen: list[str] = []

    async def _distil(partition: str) -> None:
        seen.append(partition)
        if partition == "coffer":
            raise RuntimeError("one bad partition")

    async def _partitions() -> list[str]:
        return ["coffer", "global"]

    await DistilWorker(
        distil=_distil, list_partitions=_partitions, start_delay_s=0, runs=runs
    ).run_once()

    assert seen == ["coffer", "global"]


@pytest.mark.asyncio
async def test_the_sweep_does_nothing_at_all_when_the_operator_switched_it_off(
    runs: UpkeepRunRegistry,
) -> None:
    """The switch is read per tick, not at boot, so turning it off in Settings
    does not need a daemon restart."""
    seen: list[str] = []

    async def _distil(partition: str) -> None:
        seen.append(partition)

    async def _partitions() -> list[str]:
        return ["coffer"]

    async def _off() -> bool:
        return False

    await DistilWorker(
        distil=_distil,
        list_partitions=_partitions,
        is_enabled=_off,
        start_delay_s=0,
        runs=runs,
    ).run_once()

    assert seen == []
