"""Whether the running task has been asked to stop, even if a library ate the signal.

A task is stopped by cancelling it: ``asyncio`` raises ``CancelledError`` at its
next ``await``. Most code lets that propagate, and a handler that logs a failure
and carries on (``except Exception``) never sees it, because ``CancelledError``
is not an ``Exception``.

Cleanup code can still turn it into one. SQLAlchemy's asyncio pool reacts to a
cancelled query by closing the connection; a second cancel that lands while that
close is awaited (anyio cancel scopes re-deliver theirs, and a shutdown sweep
cancels what its owner already cancelled) leaves the session to raise
``OperationalError: no active connection`` or ``ValueError: Connection closed``
instead. Measured on 2026-10-12 with the locked aiosqlite and SQLAlchemy, about
one double-cancelled query in thirteen ends that way. A loop that logs that error
and waits for its next period has swallowed its own stop: it never ends, and
whoever awaits it (the daemon's shutdown, ``asyncio.run``'s final sweep) waits
forever (ADR background-loops-stop-when-their-task-is-cancelled).

The task itself still knows: :meth:`asyncio.Task.cancelling` counts the cancel
requests nobody withdrew. A handler that would otherwise carry on asks
:func:`raise_if_stopping` first.
"""

from __future__ import annotations

import asyncio


def stop_requested() -> bool:
    """Whether the running task has a cancel request outstanding.

    ``True`` after the task was cancelled, whatever exception it is now
    handling; ``False`` outside a task and once an ``asyncio.timeout`` that
    caused the cancel has withdrawn it.
    """
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0


def raise_if_stopping(exc: BaseException) -> None:
    """Raise ``CancelledError``, chained to ``exc``, when the running task was
    asked to stop: call it first in a handler that would otherwise carry on."""
    if stop_requested():
        raise asyncio.CancelledError from exc


__all__ = ["raise_if_stopping", "stop_requested"]
