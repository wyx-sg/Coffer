"""Settling a curation item — after its pass completes, or when a pass never will.

Three ways out of the queue without a completed pass live here too: no model at
all (``promote_all``), an item too large for any pass (``shelve_oversized``) and
an item cut off every time (``give_up``).

An item is settled only once its pass completes (spec knowledge "Settle an item
only after its pass completes"): material leaves the inbox, an edited document
is stamped. A pass the recursion limit cuts off leaves its item owed, so the
next sweep retries it.

Some items are cut off every time — too much for the recursion limit however
often they are retried. Re-offered forever, such an item would burn a model pass
every sweep and re-render every agent's catalogue for nothing. So a pass counts
**consecutive** cut-offs per item, and at the :data:`MAX_CONSECUTIVE_TRUNCATIONS`-th
it gives up and settles the item the way the no-model path does: material is
**promoted** as it stands — the documents the cut-off passes wrote stay, and the
material joins them whole, so nothing it held is lost even if the passes merged
only part of it — and an edited document is stamped, since the person's edit is
already readable where they made it. The pass reports ``truncated`` with
``gave_up: true`` (and the promoted path) so a person sees it happened.

The count lives in this process, like the upkeep-run registry beside it: nothing
is written into the synced tree to hold it. A daemon restart starts it again,
which costs at most that many passes per item per restart.
"""

from __future__ import annotations

import contextlib
import threading
from typing import Any

from coffer.domain.knowledge.entry import Pending
from coffer.domain.knowledge.errors import KnowledgeFileNotFound
from coffer.infrastructure.knowledge import fs

#: Consecutive cut-offs of one item after which a pass stops retrying it.
MAX_CONSECUTIVE_TRUNCATIONS = 3


class TruncationLedger:
    """Consecutive cut-offs per item, keyed by collection uid and item label."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def record(self, collection_uid: str, label: str) -> int:
        """Count one more cut-off of the item; answer how many in a row."""
        with self._lock:
            key = (collection_uid, label)
            self._counts[key] = self._counts.get(key, 0) + 1
            return self._counts[key]

    def clear(self, collection_uid: str, label: str) -> None:
        """The item was settled, or a pass over it completed."""
        with self._lock:
            self._counts.pop((collection_uid, label), None)


def pending_items(collection: str) -> tuple[Pending, ...]:
    """What a sweep owes one collection: material first, then edits.

    New material first, because until it is merged it is knowledge no agent
    can read; an edited document is already readable as it stands.
    """
    return tuple(Pending(material=name) for name in fs.inbox_items(collection)) + tuple(
        Pending(document=relpath) for relpath in fs.edited_documents(collection)
    )


def settle(collection: str, item: Pending) -> None:
    """Mark the item absorbed: material leaves the inbox, a document is
    stamped — unless the pass retired it, in which case there is nothing left
    to stamp."""
    if item.material is not None:
        fs.discard_material(collection, item.material)
        return
    with contextlib.suppress(KnowledgeFileNotFound):
        fs.mark_curated(item.document or "")


def give_up(collection: str, item: Pending) -> list[str]:
    """Settle an item no pass can finish; answer the documents it was promoted into."""
    if item.material is not None:
        with contextlib.suppress(KnowledgeFileNotFound):
            return [fs.promote(collection, item.material).path]
        return []
    settle(collection, item)
    return []


def shelve_oversized(collection: str, item: Pending) -> dict[str, Any]:
    """Take an item no pass can hold out of the queue, and say what was done.

    Left where it was, it would be offered to every sweep and refused by every
    pass, and the collection's pending count would never drop. So material is
    promoted to a document as it stands — exactly what the no-model path does
    with it, since the model cannot merge it either — and an edited document,
    which is already a document and has nothing to promote, is stamped as seen
    so the sweep stops handing it back. Neither changes a word of the item.
    """
    if item.material is not None:
        return {"promoted": [fs.promote(collection, item.material).path]}
    settle(collection, item)
    return {"stamped": item.document or ""}


def promote_all(collection: str) -> list[str]:
    """Every inbox item made a document as it stands — the no-model path."""
    return [fs.promote(collection, name).path for name in fs.inbox_items(collection)]


__all__ = [
    "MAX_CONSECUTIVE_TRUNCATIONS",
    "TruncationLedger",
    "give_up",
    "pending_items",
    "promote_all",
    "settle",
    "shelve_oversized",
]
