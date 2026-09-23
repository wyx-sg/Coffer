"""The interval workers stand down on a target someone is already rewriting.

A timer pass and a button pass over one partition (or one collection) are two
writers over one directory, not one faster pass. The worker's answer is to
SKIP — never to queue behind it (the next sweep comes round anyway) and never
to fail the sweep (busy is an ordinary state, not a fault).

Both workers sweep **uids**, and claim them, because that is what the route the
button hits claims: the collision only happens if the two writers spell the
target the same way, and a label is exactly what can be edited between them
reading it (ADR resource-identity-is-an-immutable-uid). The uids below are
readable strings (``uid-busy``) rather than real hex, so a failure names which
target was skipped; nothing in either worker parses them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.knowledge.curate_worker import CurationWorker
from coffer.application.memory.distil_worker import DistilWorker
from coffer.application.upkeep_runs import UpkeepRunRegistry
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import fs


async def _enabled() -> bool:
    return True


class _Collections:
    """The slice of ``KnowledgeService`` the curation worker actually uses.

    It holds a collection by uid and reads the *name* off the row, once, for
    the directory ``pending_items`` walks — so a fake has to answer that one
    question. ``uid-<name>`` keeps the mapping obvious at the call sites.
    """

    async def collection(self, uid: str) -> Resource:
        now = datetime.now(tz=UTC)
        return Resource(
            id=0,
            uid=uid,
            kind="knowledge",
            name=uid.removeprefix("uid-"),
            description=None,
            config={},
            enabled=True,
            created_at=now,
            updated_at=now,
        )


@pytest.fixture
def corpus(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Two collections, each holding one piece of material no pass has merged yet.

    The curation worker asks the DIRECTORY what is owed (spec knowledge "Run
    curation on a sweep and on demand") rather than a queue, so a collection
    with nothing pending is skipped before the registry is ever consulted —
    which would make a busy/free test pass for the wrong reason.
    """
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    for name in ("busy", "free"):
        fs.create_collection_dir(name)
        fs.submit_material(name, title="Session", description="d", body="b", actor="user")
    return tmp_path / "knowledge"


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


async def test_curation_worker_skips_a_collection_already_being_curated(corpus) -> None:  # type: ignore[no-untyped-def]
    runs = UpkeepRunRegistry()
    runs.claim("knowledge", "uid-busy")
    curated: list[str] = []

    async def _curate(svc: Any, collection_uid: str, **kwargs: Any) -> dict[str, object]:
        curated.append(collection_uid)
        return {"status": "ok"}

    async def _collections() -> list[str]:
        return ["uid-busy", "uid-free"]

    worker = CurationWorker(
        service=_Collections(),  # type: ignore[arg-type]
        curate=_curate,
        is_enabled=_enabled,
        deliver=None,
        list_collections=_collections,
        runs=runs,
    )
    await worker.run_once()

    # The pass is handed the UID, not the name it resolved for the directory.
    assert curated == ["uid-free"]
    assert runs.running("knowledge", "uid-busy") is not None  # the holder keeps its key
    assert runs.running("knowledge", "uid-free") is None


async def test_a_disabled_worker_delivers_but_starts_no_pass(corpus) -> None:  # type: ignore[no-untyped-def]
    """Two different switches, and only one of them is ``auto_curate_enabled``.

    The switch is read per sweep (spec knowledge "Curate on one owner machine
    only"), so turning it off stops the very next pass rather than the one
    after a restart. Delivery is outside it on purpose: a collection created,
    deleted or re-scoped changes what each agent must be told, and that is just
    as true on a machine where curation is off or which is not the owner (see
    "Deliver the guide as the shared-master link").
    """
    started: list[str] = []
    delivered: list[int] = []

    async def _curate(svc: Any, collection_uid: str, **kwargs: Any) -> dict[str, object]:
        started.append(collection_uid)
        return {"status": "ok"}

    async def _deliver() -> None:
        delivered.append(1)

    async def _off() -> bool:
        return False

    async def _collections() -> list[str]:
        return ["uid-free"]

    await CurationWorker(
        service=_Collections(),  # type: ignore[arg-type]
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

    async def _curate(svc: Any, collection_uid: str, **kwargs: Any) -> dict[str, object]:
        started.append(collection_uid)
        return {"status": "ok"}

    async def _deliver() -> None:
        raise OSError("an agent's skill directory is unwritable")

    async def _collections() -> list[str]:
        return ["uid-free"]

    await CurationWorker(
        service=_Collections(),  # type: ignore[arg-type]
        curate=_curate,
        is_enabled=_enabled,
        deliver=_deliver,
        list_collections=_collections,
        runs=UpkeepRunRegistry(),
    ).run_once()

    assert started == ["uid-free"]
