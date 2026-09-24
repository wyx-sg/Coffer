"""The background worker that folds new knowledge into a collection's documents.

It is **on by default** (spec knowledge "Curate on one owner machine only"): it is what merges each
collection's inbox — uploads, agents' ``coffer__write`` — into the documents an
agent reads, and what carries a person's edit to one document into the rest.
A vault where it never runs is one whose new material waits unread.

It is still bounded by an owner machine, because a pass rewrites synced
content: two machines curating one corpus independently would each merge the
same material into a *different* document, and git would merge both additions
cleanly, leaving the vault holding the same knowledge twice with nothing
reported as a conflict.

Shaped like ``RetentionWorker``: one catch-up sweep shortly after boot, then on
an interval; a failing pass is logged and never kills the loop; a pending pass
never blocks shutdown, because the watermark makes a sweep idempotent and the
next boot picks up whatever was left.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from coffer.application.knowledge.curate import pending_items
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.upkeep_runs import UPKEEP_RUNS, UpkeepRunRegistry
from coffer.application.upkeep_schedule import IntervalReader, wait_for_next_pass
from coffer.domain.knowledge.entry import Pending

logger = logging.getLogger(__name__)

#: Long enough that a boot storm has settled before the first sweep.
DEFAULT_START_DELAY_S = 60.0

#: Short, because material a person just added should be readable by an agent
#: in the same sitting. One pass is one small model call, so a sweep that finds
#: nothing pending costs a directory walk.
DEFAULT_INTERVAL_S = 60.0

#: Passes one sweep may run per collection. A freshly migrated vault has
#: dozens of pending items; draining them a few at a time keeps any single
#: sweep short and lets a person watch the corpus fill in rather than waiting
#: on one long batch.
MAX_PASSES_PER_SWEEP = 5

CurateCallable = Callable[..., Awaitable[dict[str, object]]]
DeliverCallable = Callable[[], Awaitable[bool]]
EnabledCheck = Callable[[], Awaitable[bool]]
#: Yields the **uids** of the collections to sweep. Uids rather than names
#: because a pass takes minutes and rewrites a corpus: the sweep has to keep
#: naming the same collection across one, and a label can be edited while it
#: runs. It is also what the page's Curate button sends, so the claim below and
#: the route's claim are keyed on the same value without either translating.
CollectionLister = Callable[[], Awaitable[list[str]]]


async def _unset_interval() -> int | None:
    """No interval chosen — the constant above applies. The composition root
    injects a reader of the operator's setting instead."""
    return None


class CurationWorker:
    def __init__(
        self,
        *,
        service: KnowledgeService,
        curate: CurateCallable,
        deliver: DeliverCallable | None,
        is_enabled: EnabledCheck,
        list_collections: CollectionLister,
        start_delay_s: float = DEFAULT_START_DELAY_S,
        interval_s: float = DEFAULT_INTERVAL_S,
        read_interval: IntervalReader = _unset_interval,
        lock: asyncio.Lock | None = None,
        runs: UpkeepRunRegistry = UPKEEP_RUNS,
        max_passes_per_sweep: int = MAX_PASSES_PER_SWEEP,
    ) -> None:
        self._service = service
        self._curate = curate
        self._deliver = deliver
        self._is_enabled = is_enabled
        self._list_collections = list_collections
        self._start_delay_s = start_delay_s
        self._interval_s = interval_s
        self._read_interval = read_interval
        # The vault-write lock a converge round also takes (spec vault-sync
        # "Never overlap a tidy pass and a round"): a pass and a round both rewrite vault
        # content, and an export taken half-way through a rewrite is a torn
        # snapshot that git reads as a deliberate change. None on a vault with
        # no sync wired, where there is nothing to interleave with.
        self._lock = lock
        # The same table the page's button claims against. The lock above is
        # vault-wide; this one is per-collection, which is the collision this
        # worker actually has with a person pressing Curate.
        self._runs = runs
        self._max_passes = max_passes_per_sweep
        # Items whose last pass the recursion limit cut off, keyed by collection
        # uid. They go behind the rest of the inbox next sweep (see ``_drain``).
        self._cut_off: set[tuple[str, Pending]] = set()

    async def run_forever(self) -> None:
        await asyncio.sleep(self._start_delay_s)
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed sweep must never end the loop: the next one is a
                # fresh attempt, and the watermark tells it what is still owed.
                logger.warning("knowledge.curate_worker.sweep_failed", exc_info=True)
            # The operator's interval is re-read as the wait runs, so a change
            # in Settings lands within a slice rather than at the end of a wait
            # this worker committed to hours ago.
            await wait_for_next_pass(self._read_interval, default_s=self._interval_s)

    async def run_once(self) -> None:
        """Re-deliver the skills, then sweep — or not, when curation is off."""
        # Delivery runs on every tick and OUTSIDE the enabled check, because it is not
        # part of curating: a collection created, deleted, enabled or disabled changes
        # what every agent must be told, and that is true on a machine where curation is
        # switched off or which is not the owner (see "Deliver the guide as the
        # shared-master link"). It is cheap and skips a copy that already matches.
        if self._deliver is not None:
            try:
                await self._deliver()
            except Exception:
                logger.warning("knowledge.curate_worker.delivery_failed", exc_info=True)
        if not await self._is_enabled():
            return
        if self._lock is None:
            await self._sweep()
            return
        async with self._lock:
            await self._sweep()

    async def _sweep(self) -> None:
        for uid in await self._list_collections():
            try:
                await self._drain(uid)
            except asyncio.CancelledError:
                raise
            except Exception:
                # One collection failing must not skip the rest.
                logger.warning(
                    "knowledge.curate_worker.collection_failed",
                    extra={"collection_uid": uid},
                    exc_info=True,
                )

    async def _drain(self, uid: str) -> None:
        """Up to ``max_passes`` pending items of one collection, one pass each.

        The collection is held as a uid and the *name* is read off its row,
        once, because the name is only ever wanted for one thing here: it is
        the directory ``pending_items`` walks. The pass itself is handed the
        uid and resolves the row again on its own — a second cheap lookup, in
        exchange for a pass that cannot be aimed at a collection by a label
        this worker read some seconds earlier.
        """
        collection = (await self._service.collection(uid)).name
        if not await asyncio.to_thread(pending_items, collection):
            return
        # Skip, never queue: a collection someone is already curating by hand
        # does not need a second pass behind the first, and the next sweep
        # comes round to it anyway. Busy is an ordinary state of a collection,
        # so it is not logged as a failure.
        async with self._runs.claimed(KIND_KNOWLEDGE, uid) as claimed:
            if not claimed:
                logger.debug(
                    "knowledge.curate_worker.collection_busy",
                    extra={"collection": collection},
                )
                return
            # Re-read inside the claim. The cheap check above only decided
            # whether the claim was worth taking; between it and here a manual
            # pass may have absorbed some of those items, and curating one
            # already settled is a wasted model call that rewrites documents
            # for nothing.
            pending = await asyncio.to_thread(pending_items, collection)
            # An item cut off last time goes behind the rest (a stable sort keeps
            # each group oldest first): otherwise it is first in line every sweep
            # and, with few passes a sweep, the rest of the inbox waits until the
            # pass gives up on it (``curate_settle``).
            self._cut_off = {k for k in self._cut_off if k[0] != uid or k[1] in pending}
            pending = tuple(sorted(pending, key=lambda p: (uid, p) in self._cut_off))
            for item in pending[: self._max_passes]:
                outcome = await self._curate(self._service, uid, item=item, actor="system")
                status = str(outcome.get("status", ""))
                if status == "truncated" and not outcome.get("gave_up"):
                    self._cut_off.add((uid, item))
                else:
                    self._cut_off.discard((uid, item))
                if status in {"no_model", "failed"}:
                    # No model is an installation-wide fact — and the pass has
                    # already promoted the inbox as it stands — and a failed
                    # loop is likely to fail again on the next item in the same
                    # sweep. Either way, stop here and let the next sweep try.
                    logger.info(
                        "knowledge.curate_worker.stopping_sweep",
                        extra={"collection": collection, "status": status},
                    )
                    return
                # ``truncated`` (the recursion limit cut the pass off) leaves
                # its item pending but does NOT stop the sweep: stopping on it
                # would starve the rest. The loop walks a snapshot, so it is
                # not retried until the next sweep.
