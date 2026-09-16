"""The interval workers stand down on a target someone is already rewriting.

A timer pass and a button pass over one partition (or one collection) are two
writers over one directory, not one faster pass. The worker's answer is to
SKIP — never to queue behind it (the next sweep comes round anyway) and never
to fail the sweep (busy is an ordinary state, not a fault).
"""

from __future__ import annotations

from coffer.application.knowledge.tidy_worker import TidyWorker
from coffer.application.memory.organise_worker import OrganiseWorker
from coffer.application.upkeep_runs import UpkeepRunRegistry


async def _enabled() -> bool:
    return True


async def test_organise_worker_skips_a_partition_already_being_organised() -> None:
    runs = UpkeepRunRegistry()
    runs.claim("memory", "busy")
    organised: list[str] = []

    async def _organise(partition: str) -> object:
        organised.append(partition)
        return object()

    async def _partitions() -> list[str]:
        return ["busy", "free"]

    worker = OrganiseWorker(organise=_organise, list_partitions=_partitions, runs=runs)
    await worker.run_once()

    # Skipped, not queued — and the rest of the sweep still happened.
    assert organised == ["free"]


async def test_organise_worker_gives_each_partition_s_key_back() -> None:
    """A sweep that held its claims would lock the button out afterwards."""
    runs = UpkeepRunRegistry()

    async def _organise(partition: str) -> object:
        assert runs.running("memory", partition) is not None
        return object()

    async def _partitions() -> list[str]:
        return ["coffer"]

    await OrganiseWorker(organise=_organise, list_partitions=_partitions, runs=runs).run_once()

    assert runs.list_running() == []


async def test_tidy_worker_skips_a_collection_already_being_tidied() -> None:
    runs = UpkeepRunRegistry()
    runs.claim("knowledge", "busy")
    tidied: list[str] = []

    async def _tidy(svc, collection, *, actor):  # type: ignore[no-untyped-def]
        tidied.append(collection)
        return {"status": "ok"}

    async def _collections() -> list[str]:
        return ["busy", "free"]

    worker = TidyWorker(
        service=object(),  # type: ignore[arg-type]  # passed straight through to _tidy
        tidy=_tidy,
        is_enabled=_enabled,
        list_collections=_collections,
        runs=runs,
    )
    await worker.run_once()

    assert tidied == ["free"]
    assert runs.running("knowledge", "busy") is not None  # the holder keeps its key
    assert runs.running("knowledge", "free") is None
