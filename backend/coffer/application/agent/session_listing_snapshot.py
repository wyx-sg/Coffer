"""SnapshotSessionSource — the last answer of a native-session source, in memory.

Listing an agent's own sessions is slow for some agents (Codex's ``thread/list``
over a short-lived ``codex app-server`` costs one to two seconds however small
the page) and the Conversations page asks again for every page it has loaded.
This wrapper keeps the last answer per ``(config dir, search, limit, position)``
and serves it stale-while-revalidate:

* younger than ``fresh_s`` — returned, the source is not asked;
* younger than ``max_age_s`` — returned at once, and ONE background refresh per
  key replaces it;
* missing or older — the caller waits for one fetch (concurrent callers for the
  same key share it).

The snapshot lives in this process's memory only: never on disk, never synced,
bounded by an LRU cap, and gone with the process. ``rename`` and ``delete`` pass
through to the wrapped source and then drop every entry for that config dir, so
the next read is fresh. A failed background refresh keeps the old entry; a failed
foreground fetch propagates, so an unavailable agent is still reported.
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from coffer.application.agent.native_session_service import NativeSessionSource, SourcePage
from coffer.application.runtime.supervisor import spawn

_log = logging.getLogger(__name__)

_Key = tuple[str, str | None, int, str | None]
# Inside the class, ``list`` names the method, so the annotation needs an alias.
_Pos = list[Any] | None
# A fetch's outcome: the page, or what the source raised (returned, not raised, so
# the supervisor does not log an unavailable agent as a crashed task).
_Outcome = SourcePage | Exception


class SnapshotSessionSource:
    """A :class:`NativeSessionSource` that remembers its inner source's answers."""

    def __init__(
        self,
        inner: NativeSessionSource,
        *,
        fresh_s: float = 5.0,
        max_age_s: float = 300.0,
        max_entries: int = 32,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._fresh_s = fresh_s
        self._max_age_s = max_age_s
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[_Key, tuple[float, SourcePage]] = OrderedDict()
        self._inflight: dict[_Key, asyncio.Task[_Outcome]] = {}
        self._background: set[asyncio.Task[Any]] = set()
        # Bumped per config dir by a rename or delete: a fetch that started before
        # the change still answers its callers but is not kept.
        self._generation: dict[str, int] = {}

    @staticmethod
    def _key(config_dir: pathlib.Path, q: str | None, limit: int, position: _Pos) -> _Key:
        pos = None if position is None else json.dumps(position, sort_keys=True, default=str)
        return (str(config_dir), q, limit, pos)

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: _Pos
    ) -> SourcePage:
        key = self._key(config_dir, q, limit, position)
        entry = self._entries.get(key)
        if entry is not None:
            age = self._clock() - entry[0]
            if age < self._max_age_s:
                self._entries.move_to_end(key)
                if age >= self._fresh_s:
                    self._refresh_in_background(key, config_dir, q, limit, position)
                return entry[1]
            del self._entries[key]
        return await self._fetch(key, config_dir, q, limit, position)

    def _task(
        self, key: _Key, config_dir: pathlib.Path, q: str | None, limit: int, pos: _Pos
    ) -> asyncio.Task[_Outcome]:
        """The one in-flight fetch for ``key`` (started if there is none)."""
        task = self._inflight.get(key)
        if task is None:
            task = spawn(self._run(key, config_dir, q, limit, pos), name="agent-sessions-snapshot")
            self._inflight[key] = task
        return task

    async def _run(
        self, key: _Key, config_dir: pathlib.Path, q: str | None, limit: int, pos: _Pos
    ) -> _Outcome:
        generation = self._generation.get(key[0], 0)
        task = asyncio.current_task()
        try:
            page = await self._inner.list(config_dir, q=q, limit=limit, position=pos)
        except Exception as exc:
            return exc
        finally:
            if self._inflight.get(key) is task:
                del self._inflight[key]
        if self._generation.get(key[0], 0) != generation:
            return page  # read before a rename or delete: answer, but do not keep
        self._entries[key] = (self._clock(), page)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        return page

    async def _fetch(
        self, key: _Key, config_dir: pathlib.Path, q: str | None, limit: int, pos: _Pos
    ) -> SourcePage:
        # shield: one caller being cancelled must not cancel the fetch the others share.
        outcome = await asyncio.shield(self._task(key, config_dir, q, limit, pos))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _refresh_in_background(
        self, key: _Key, config_dir: pathlib.Path, q: str | None, limit: int, pos: _Pos
    ) -> None:
        if key in self._inflight:
            return
        task = self._task(key, config_dir, q, limit, pos)
        self._background.add(task)
        task.add_done_callback(self._background_done)

    def _background_done(self, task: asyncio.Task[Any]) -> None:
        self._background.discard(task)
        if task.cancelled():
            return
        exc = task.result()
        if isinstance(exc, Exception):
            _log.warning("session snapshot refresh failed, keeping the old answer: %s", exc)

    def _drop(self, config_dir: pathlib.Path) -> None:
        name = str(config_dir)
        for key in [k for k in self._entries if k[0] == name]:
            del self._entries[key]
        self._generation[name] = self._generation.get(name, 0) + 1
        # A fetch in flight keeps answering whoever awaits it, but it no longer
        # stands for this key: the next read starts a fresh one.
        for key in [k for k in self._inflight if k[0] == name]:
            del self._inflight[key]

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None:
        try:
            await self._inner.rename(config_dir, session_id, title)
        finally:
            self._drop(config_dir)

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None:
        try:
            await self._inner.delete(config_dir, session_id)
        finally:
            self._drop(config_dir)

    async def aclose(self) -> None:
        """Cancel every fetch still in flight; the snapshot is then empty."""
        tasks = list({*self._inflight.values(), *self._background})
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._inflight.clear()
        self._background.clear()
        self._entries.clear()


__all__ = ["SnapshotSessionSource"]
