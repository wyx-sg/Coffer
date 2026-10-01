"""Supervised background tasks: named, crash-logged, restarted on request, cancelled at shutdown.

The daemon used to start its background work with some fifty bare
``asyncio.create_task`` calls. Each owner kept (or forgot to keep) its own
reference, and a task that raised died quietly: ``asyncio`` reports an
exception nobody retrieved only when the task is garbage-collected, as an
unstructured "Task exception was never retrieved" on stderr — or not at all, if
the owner kept the reference and never awaited it. A Telegram poll loop that hit
a bug stopped receiving messages and said nothing.

Everything that outlives the call that started it goes through here instead:

* :meth:`TaskSupervisor.spawn` — one task, with a name. If it raises, a
  ``runtime.task.crashed`` line with the task's name and the exception reaches
  ``daemon.log`` the moment it ends, and the crash is counted.
* :meth:`TaskSupervisor.spawn_restarting` — a long-lived loop whose owner wants
  it back after a crash. It is re-run after a backoff that doubles up to a cap,
  and each crash is logged and counted the same way. A clean return ends it.
* :meth:`TaskSupervisor.shutdown` — cancels whatever is still running, bounded,
  so the daemon's teardown never waits on a task its owner forgot to stop.

The helper never swallows cancellation, and it does not catch what the task
handles itself: a task that logs its own failures and carries on is not a
crash. Tasks an owner awaits in the same function — the two sides of an
``asyncio.wait`` race, a shielded write — are structured concurrency, not
background work, and stay bare; ``scripts/check_bare_tasks.py`` holds the list.

One process-wide supervisor (:func:`tasks`) because the tasks it owns are
started from deep inside kinds that have no composition-root handle to be
given, and the crash count it reports is the daemon's, not any kind's.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_logger = logging.getLogger(__name__)

#: How many recent crashes the status surface can show.
_RECENT_CRASHES = 20


@dataclass(frozen=True)
class Restart:
    """How a restarting task backs off: ``initial`` seconds, doubling to ``cap``."""

    initial: float = 1.0
    cap: float = 60.0


@dataclass(frozen=True)
class Crash:
    """One task that ended by raising."""

    task: str
    error: str
    at: datetime
    restarting: bool


@dataclass(frozen=True)
class SupervisionStats:
    """What the supervisor reports on ``GET /api/v1/daemon/status``."""

    running: int
    crashes: int
    last_crash: Crash | None


class TaskSupervisor:
    """Owns the daemon's background tasks. See the module docstring."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._crashes = 0
        self._recent: deque[Crash] = deque(maxlen=_RECENT_CRASHES)
        self._closing = False

    # -- starting -----------------------------------------------------------

    def spawn[T](self, coro: Coroutine[Any, Any, T], *, name: str) -> asyncio.Task[T]:
        """Start ``coro`` as a named, supervised task and return it.

        The owner may still cancel or await the returned task; supervision only
        adds the crash line and the shutdown sweep.
        """
        task = asyncio.get_running_loop().create_task(coro, name=name)
        # A task whose loop has closed can never finish; holding it would pin
        # its coroutine (and whatever pipes or clients it holds) for the life of
        # the process — which is every test after the one whose loop it was.
        self._tasks = {t for t in self._tasks if not t.get_loop().is_closed()}
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def spawn_restarting(
        self,
        factory: Callable[[], Coroutine[Any, Any, None]],
        *,
        name: str,
        restart: Restart | None = None,
    ) -> asyncio.Task[None]:
        """Run ``factory()`` as a named task, and run it again whenever it crashes.

        ``factory`` is called for every attempt, so each gets a fresh coroutine.
        A clean return ends supervision; cancelling the returned task stops it
        for good.
        """
        return self.spawn(self._restarting(factory, name, restart or Restart()), name=name)

    async def _restarting(
        self,
        factory: Callable[[], Coroutine[Any, Any, None]],
        name: str,
        restart: Restart,
    ) -> None:
        delay = restart.initial
        while True:
            try:
                await factory()
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._record(name, exc, restarting=not self._closing)
                if self._closing:
                    return
            await asyncio.sleep(delay)
            delay = min(delay * 2, restart.cap)

    # -- crash bookkeeping --------------------------------------------------

    def _on_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self._record(task.get_name(), exc, restarting=False)

    def _record(self, name: str, exc: BaseException, *, restarting: bool) -> None:
        self._crashes += 1
        self._recent.append(
            Crash(
                task=name,
                # The class name only: ``/daemon/status`` answers without a token,
                # and an exception's text can carry what it failed on (a reflected
                # key, a path). The message and traceback go to daemon.log.
                error=type(exc).__name__,
                at=datetime.now(tz=UTC),
                restarting=restarting,
            )
        )
        _logger.error(
            "runtime.task.crashed",
            exc_info=(type(exc), exc, exc.__traceback__),
            extra={"task": name, "error": type(exc).__name__, "restarting": restarting},
        )

    # -- reading ------------------------------------------------------------

    def stats(self) -> SupervisionStats:
        return SupervisionStats(
            running=sum(1 for t in self._tasks if not t.done()),
            crashes=self._crashes,
            last_crash=self._recent[-1] if self._recent else None,
        )

    def recent_crashes(self) -> list[Crash]:
        return list(self._recent)

    def running_names(self) -> list[str]:
        return sorted(t.get_name() for t in self._tasks if not t.done())

    # -- stopping -----------------------------------------------------------

    async def shutdown(self, timeout: float = 5.0) -> list[str]:
        """Cancel every task still running on this loop; return the names cancelled.

        Owners stop their own tasks first, in the order the teardown needs; this
        is the sweep after them. Bounded by ``timeout`` so a task that ignores
        cancellation cannot hold the daemon up.
        """
        self._closing = True
        try:
            loop = asyncio.get_running_loop()
            pending = [t for t in self._tasks if not t.done() and t.get_loop() is loop]
            for task in pending:
                task.cancel()
            if pending:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait(pending, timeout=timeout)
            stuck = [t.get_name() for t in pending if not t.done()]
            if stuck:
                _logger.warning("runtime.task.shutdown_timed_out", extra={"tasks": stuck})
            return sorted(t.get_name() for t in pending)
        finally:
            self._closing = False


_TASKS = TaskSupervisor()


def tasks() -> TaskSupervisor:
    """The daemon's one supervisor."""
    return _TASKS


def spawn[T](coro: Coroutine[Any, Any, T], *, name: str) -> asyncio.Task[T]:
    """:meth:`TaskSupervisor.spawn` on the daemon's supervisor."""
    return _TASKS.spawn(coro, name=name)


def spawn_restarting(
    factory: Callable[[], Coroutine[Any, Any, None]],
    *,
    name: str,
    restart: Restart | None = None,
) -> asyncio.Task[None]:
    """:meth:`TaskSupervisor.spawn_restarting` on the daemon's supervisor."""
    return _TASKS.spawn_restarting(factory, name=name, restart=restart)
