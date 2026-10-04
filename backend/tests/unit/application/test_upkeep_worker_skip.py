"""The distil worker stands down on a partition someone is already rewriting.

A timer pass and a button pass over one partition are two writers over one
directory, not one faster pass. The worker's answer is to SKIP — never to queue
behind it (the next sweep comes round anyway) and never to fail the sweep (busy
is an ordinary state, not a fault).

The worker sweeps **uids**, and claims them, because that is what the route the
button hits claims: the collision only happens if the two writers spell the
target the same way, and a label is exactly what can be edited between them
reading it (ADR identity-is-the-uid-inside-the-file). The uids below are
readable strings (``uid-busy``) rather than real hex, so a failure names which
target was skipped; nothing in the worker parses them.
"""

from __future__ import annotations

from coffer.application.memory.distil_worker import DistilWorker
from coffer.application.upkeep_runs import UpkeepRunRegistry


async def test_distil_worker_skips_a_partition_already_being_distilled() -> None:
    runs = UpkeepRunRegistry()
    runs.claim("memory", "uid-busy")
    distilled: list[str] = []

    async def _distil(uid: str) -> object:
        distilled.append(uid)
        return object()

    async def _partitions() -> list[str]:
        return ["uid-busy", "uid-free"]

    worker = DistilWorker(distil=_distil, list_partitions=_partitions, runs=runs)
    await worker.run_once()

    # Skipped, not queued — and the rest of the sweep still happened.
    assert distilled == ["uid-free"]


async def test_distil_worker_gives_each_partition_s_key_back() -> None:
    """A sweep that held its claims would lock the button out afterwards."""
    runs = UpkeepRunRegistry()

    async def _distil(uid: str) -> object:
        assert runs.running("memory", uid) is not None
        return object()

    async def _partitions() -> list[str]:
        return ["uid-coffer"]

    await DistilWorker(distil=_distil, list_partitions=_partitions, runs=runs).run_once()

    assert runs.list_running() == []
