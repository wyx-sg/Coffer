"""``Changed`` hints for resource changes the resource store did not make
itself (spec vault-storage; ADR one-level-triggered-reconciler-compares-parameters).

A write through ``ResourceService`` is announced by ``HintingResourceRepo``.
But the vault has other writers: a person's hand edit that the scanner settles,
a sync round's checkout, a restore, a join's "take the other version". Each of
them reaches the vault writer's listeners with the paths it changed, and the
resource store answers each such commit here: it re-reads the effective
resources and emits one ``Changed`` per resource whose file moved — an upsert
at the resource's new revision, or a delete at its last revision plus one — so
the reconciler and the event stream see them exactly as they see an API write.

The store's own commits are marked (:meth:`ChangeAnnouncer.own`) and skipped:
the hinting wrapper already announces them, and a second hint would only make
the event stream say everything twice.

The sink is the event loop's (the reconciler's wake event and the broker are
not thread-safe), while a listener runs on whatever thread committed — a sync
round or the scanner runs in a worker thread — so a hint from another thread
is handed to the loop with ``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

from coffer.domain.reconcile import Changed
from coffer.domain.resource import Resource

logger = logging.getLogger(__name__)

Sink = Callable[[Changed], None]


@dataclass(frozen=True)
class Known:
    """What the store last saw at one vault path."""

    uid: str
    kind: str
    rev: int


class ChangeAnnouncer:
    """Turns the paths of a commit into ``Changed`` hints."""

    def __init__(self) -> None:
        self._sink: Sink | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._local = threading.local()
        self._known: dict[str, Known] = {}

    @property
    def active(self) -> bool:
        return self._sink is not None

    def set_sink(self, sink: Sink) -> None:
        """Announce to ``sink``; called on the event loop, whose loop every
        hint from another thread is handed to."""
        self._sink = sink
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    @contextmanager
    def own(self) -> Iterator[None]:
        """Mark the commits made inside as the store's own."""
        previous = getattr(self._local, "own", False)
        self._local.own = True
        try:
            yield
        finally:
            self._local.own = previous

    def owning(self) -> bool:
        return bool(getattr(self._local, "own", False))

    def remember(self, known: Mapping[str, Known]) -> None:
        self._known = dict(known)

    def known(self) -> dict[str, Known]:
        return dict(self._known)

    def emit(self, changed: Changed) -> None:
        sink = self._sink
        if sink is None:
            return
        loop = self._loop
        try:
            running: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        try:
            if loop is None or running is loop or loop.is_closed():
                sink(changed)
            else:
                loop.call_soon_threadsafe(sink, changed)
        except Exception:
            logger.warning("vault.resource_hint_failed", exc_info=True)

    def announce(
        self,
        paths: Iterable[str],
        before: Mapping[str, Known],
        after: Mapping[str, Known],
        resources: Mapping[str, Resource],
    ) -> None:
        """One hint per resource a commit of ``paths`` changed."""
        seen: set[tuple[str, str]] = set()
        for path in paths:
            now = after.get(path)
            if now is not None and (now.uid, "upsert") not in seen:
                seen.add((now.uid, "upsert"))
                current = resources.get(now.uid)
                rev = current.rev if current is not None else now.rev
                self.emit(Changed(now.kind, now.uid, rev, "upsert"))
            old = before.get(path)
            if old is not None and old.uid not in resources and (old.uid, "delete") not in seen:
                seen.add((old.uid, "delete"))
                self.emit(Changed(old.kind, old.uid, old.rev + 1, "delete"))


__all__ = ["ChangeAnnouncer", "Known", "Sink"]
