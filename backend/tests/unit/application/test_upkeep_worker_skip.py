"""The interval workers stand down on a target someone is already rewriting.

A timer pass and a button pass over one partition (or one collection) are two
writers over one directory, not one faster pass. The worker's answer is to
SKIP — never to queue behind it (the next sweep comes round anyway) and never
to fail the sweep (busy is an ordinary state, not a fault).
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.knowledge.curate_worker import CurationWorker
from coffer.application.memory.distil_worker import DistilWorker
from coffer.application.upkeep_runs import UpkeepRunRegistry
from coffer.infrastructure.knowledge import fs


async def _enabled() -> bool:
    return True


@pytest.fixture
def corpus(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Two collections, each holding one source no pass has absorbed yet.

    The curation worker asks the DIRECTORY what is owed (spec knowledge
    FR-022) rather than a queue, so a collection with nothing pending is
    skipped before the registry is ever consulted — which would make a
    busy/free test pass for the wrong reason.
    """
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    for name in ("busy", "free"):
        fs.create_collection_dir(name)
        fs.write_file(
            directory=f"{name}/sources", title="Session", description="d", body="b", actor="user"
        )
    return tmp_path / "knowledge"


async def test_distil_worker_skips_a_partition_already_being_distilled() -> None:
    runs = UpkeepRunRegistry()
    runs.claim("memory", "busy")
    distilled: list[str] = []

    async def _distil(partition: str) -> object:
        distilled.append(partition)
        return object()

    async def _partitions() -> list[str]:
        return ["busy", "free"]

    worker = DistilWorker(distil=_distil, list_partitions=_partitions, runs=runs)
    await worker.run_once()

    # Skipped, not queued — and the rest of the sweep still happened.
    assert distilled == ["free"]


async def test_distil_worker_gives_each_partition_s_key_back() -> None:
    """A sweep that held its claims would lock the button out afterwards."""
    runs = UpkeepRunRegistry()

    async def _distil(partition: str) -> object:
        assert runs.running("memory", partition) is not None
        return object()

    async def _partitions() -> list[str]:
        return ["coffer"]

    await DistilWorker(distil=_distil, list_partitions=_partitions, runs=runs).run_once()

    assert runs.list_running() == []


async def test_curation_worker_skips_a_collection_already_being_curated(corpus) -> None:  # type: ignore[no-untyped-def]
    runs = UpkeepRunRegistry()
    runs.claim("knowledge", "busy")
    curated: list[str] = []

    async def _curate(svc: Any, collection: str, **kwargs: Any) -> dict[str, object]:
        curated.append(collection)
        return {"status": "ok"}

    async def _collections() -> list[str]:
        return ["busy", "free"]

    worker = CurationWorker(
        service=object(),  # type: ignore[arg-type]  # passed straight through to _curate
        curate=_curate,
        is_enabled=_enabled,
        deliver=None,
        list_collections=_collections,
        runs=runs,
    )
    await worker.run_once()

    assert curated == ["free"]
    assert runs.running("knowledge", "busy") is not None  # the holder keeps its key
    assert runs.running("knowledge", "free") is None


async def test_a_disabled_worker_delivers_but_starts_no_pass(corpus) -> None:  # type: ignore[no-untyped-def]
    """Two different switches, and only one of them is ``auto_curate_enabled``.

    The switch is read per sweep (spec knowledge FR-032), so turning it off
    stops the very next pass rather than the one after a restart. Delivery is
    outside it on purpose: a collection created, deleted or re-scoped changes
    what each agent must be told, and that is just as true on a machine where
    curation is off or which is not the owner (FR-052).
    """
    started: list[str] = []
    delivered: list[int] = []

    async def _curate(svc: Any, collection: str, **kwargs: Any) -> dict[str, object]:
        started.append(collection)
        return {"status": "ok"}

    async def _deliver() -> None:
        delivered.append(1)

    async def _off() -> bool:
        return False

    async def _collections() -> list[str]:
        return ["free"]

    await CurationWorker(
        service=object(),  # type: ignore[arg-type]
        curate=_curate,
        is_enabled=_off,
        deliver=_deliver,
        list_collections=_collections,
        runs=UpkeepRunRegistry(),
    ).run_once()

    assert started == []
    assert delivered == [1]


async def test_a_delivery_that_raises_does_not_stop_the_sweep(corpus) -> None:  # type: ignore[no-untyped-def]
    """Delivery is best-effort: the corpus stays readable at paths a person can
    give an agent, so a failure there must not cost the curation it precedes."""
    started: list[str] = []

    async def _curate(svc: Any, collection: str, **kwargs: Any) -> dict[str, object]:
        started.append(collection)
        return {"status": "ok"}

    async def _deliver() -> None:
        raise OSError("an agent's skill directory is unwritable")

    async def _collections() -> list[str]:
        return ["free"]

    await CurationWorker(
        service=object(),  # type: ignore[arg-type]
        curate=_curate,
        is_enabled=_enabled,
        deliver=_deliver,
        list_collections=_collections,
        runs=UpkeepRunRegistry(),
    ).run_once()

    assert started == ["free"]
