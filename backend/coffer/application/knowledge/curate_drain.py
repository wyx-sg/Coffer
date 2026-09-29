"""Curate now: run passes over one collection until nothing that was pending
is left (spec knowledge "Run curation on a sweep and on demand").

The sweep drains a few items per tick; a person pressing Curate now wants the
collection done. So the manual trigger reads the pending list once — inbox
items oldest first, then documents edited out of band — and runs **one pass per
item, one at a time**, each still bounded to eight writes. That list is the
run's *m*: items that arrive while it runs wait for the next run or sweep, so
the progress it reports (*n of m*) is honest about what it set out to do.

It stops at the first ``failed`` pass, leaving the rest pending — one broken
item must not hide behind a success count — and after a ``no_model`` pass,
which has already promoted the whole inbox as it stands. ``truncated`` and
``too_large`` do not stop it: their items are either left owed (behind the
rest, for the sweep) or settled, exactly as in the sweep.

The vault-write lock is taken per pass, not for the whole run, so a sync round
is not held off for the minutes a drain can take; the caller holds the
collection's upkeep claim for the whole run, which is what refuses a second
trigger with 409.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.knowledge.curate_settle import pending_items
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.entry import Pending

CurateCallable = Callable[..., Awaitable[dict[str, Any]]]
#: Told ``(done, total)`` once before the first pass and after every pass.
ProgressSink = Callable[[int, int], Awaitable[None]]
LockFactory = Callable[[], contextlib.AbstractAsyncContextManager[Any]]

#: A pass outcome after which the run does not go on.
_STOPS = frozenset({"failed", "no_model"})


@contextlib.asynccontextmanager
async def _no_lock() -> Any:
    yield


async def drain(
    curate: CurateCallable,
    service: KnowledgeService,
    collection_uid: str,
    *,
    document: str | None = None,
    actor: str = "user",
    lock: LockFactory = _no_lock,
    on_progress: ProgressSink | None = None,
) -> dict[str, Any]:
    """Run the passes and answer every one's outcome, in order.

    ``status`` is ``up_to_date`` when nothing was pending (or ``no_model``,
    which a pass reports before it looks), ``failed`` or ``no_model`` when the
    run stopped at such a pass, and ``ok`` when it worked through its list.
    Given ``document``, exactly one pass runs, over that document.
    """
    collection = (await service.collection(collection_uid)).name
    if document:
        items: tuple[Pending, ...] = (Pending(document=document),)
    else:
        items = await asyncio.to_thread(pending_items, collection)
    total = len(items)

    async def progress(done: int) -> None:
        if on_progress is not None:
            with contextlib.suppress(Exception):
                await on_progress(done, total)

    await progress(0)
    if not items:
        # Nothing pending: the pass says so itself (``up_to_date``), or says
        # there is no model — the order "Report every pass outcome as a
        # status" gives, and what a caller of the old one-pass trigger saw.
        async with lock():
            outcome = await curate(service, collection_uid, item=None, actor=actor)
        return _answer(collection, total, [outcome])

    passes: list[dict[str, Any]] = []
    for done, item in enumerate(items, start=1):
        if not document and item not in await asyncio.to_thread(pending_items, collection):
            # Settled or removed since the list was read — nothing left to do.
            await progress(done)
            continue
        async with lock():
            outcome = await curate(service, collection_uid, item=item, actor=actor)
        passes.append(outcome)
        await progress(done)
        if outcome.get("status") in _STOPS:
            break
    return _answer(collection, total, passes)


def _answer(collection: str, total: int, passes: list[dict[str, Any]]) -> dict[str, Any]:
    last = str(passes[-1].get("status", "")) if passes else "up_to_date"
    status = last if last in {*_STOPS, "up_to_date"} else "ok"
    return {"collection": collection, "status": status, "total": total, "passes": passes}


__all__ = ["drain"]
