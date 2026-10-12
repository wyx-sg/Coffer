# Background Loops Stop When Their Task Is Cancelled, Even If Cleanup Raised Something Else

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [Background Work Runs Supervised, and Every Record Carries One Correlation Id](background-work-runs-supervised-and-correlated.md), [Background Workers Wake on Events, Fall Back Rarely, and Stop When Nothing Needs Them](background-workers-wake-on-events.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](one-level-triggered-reconciler-compares-parameters.md)

## Context

From 2026-10-05 the integration tier failed every few runs with one test hitting
the 300 s `pytest-timeout`, and a re-run passed. The test was a different one
each time (`test_custom_tool_environments`, `test_custom_tool_management`,
`test_agent_registry_rest_scenarios`, …) and the timeout was never in the test
body: it was in the `TestClient` teardown, joining the thread that runs the
app's event loop. The thread dump showed that loop inside
`asyncio.Runner.close()` → `_cancel_all_tasks`, waiting for a task that had been
cancelled and had not finished. Just before the hang, both logs (runs
38204388721 and 38198273174) show the same two lines:

```
ERROR  Exception terminating connection <AdaptedConnection <aiosqlite...>>  (CancelledError)
WARNING reconcile.target_failed skill_link: OperationalError('(sqlite3.OperationalError) no active connection')
```

The mechanism, reproduced with the locked SQLAlchemy 2.0.50 and aiosqlite
0.22.1:

1. A task is cancelled while a query is in flight. SQLAlchemy invalidates the
   connection and awaits a graceful close of it.
2. A second cancel lands during that close. Coffer's shutdown cancels a worker
   and its supervisor's sweep cancels it again; anyio cancel scopes re-deliver
   theirs; `asyncio.Runner` cancels whatever is left. The close is abandoned,
   the connection is force-closed, and the session's own cleanup then fails on
   it, raising `OperationalError: no active connection` or `ValueError:
   Connection closed` in place of `CancelledError`.
3. That is an `Exception`, so a loop's "log it and carry on" handler catches it,
   logs a failed run and waits for its next period. The task's stop has been
   swallowed: it never ends, and whoever waits for it waits for ever.

Cancelling a task once mid-query never did this (3 000 of 3 000 attempts ended
cancelled). Cancelling it twice a moment apart did in 225 of 3 000 (7.5 %). The
daemon's own shutdown is exposed the same way: `asyncio.run` ends with the same
`_cancel_all_tasks` and would hang on the same loop.

## How comparable runtimes handle it

| Runtime | Rule |
| --- | --- |
| Python `asyncio` (3.11+) | `Task.cancelling()` counts cancel requests not withdrawn by `uncancel()`; `asyncio.timeout` and `TaskGroup` read it to tell their own cancel from an outside one |
| Trio / anyio | A cancelled scope re-raises `Cancelled` at every later checkpoint, so swallowing it once is not enough to escape |
| Go `context` | A worker checks `ctx.Err()` after any failure before retrying; a cancelled context ends the loop whatever error came back |
| Kotlin coroutines | `catch (e: Exception)` around a suspend call must call `ensureActive()` (or rethrow `CancellationException`) before carrying on |

The shared rule: an error caught after a stop was requested is not a reason to
keep going; the stop request is checked, not inferred from the exception type.

## Options Considered

### Option A — re-run flaky jobs, or raise the timeout

- **Good:** no code change.
- **Bad:** the task never ends, so no timeout is long enough; a re-run only
  rolls the dice again. It also leaves the daemon's real shutdown exposed, and
  every re-run costs the owner a click (the integration cannot re-run jobs).

### Option B — never cancel a worker twice

Make every owner wait for its worker to finish after one cancel, and keep the
supervisor's sweep and `asyncio.Runner` from cancelling again.

- **Good:** removes the trigger at its source in Coffer's own shutdown.
- **Bad:** not ours to guarantee. anyio scopes re-deliver by design,
  `asyncio.Runner` cancels whatever is still pending, and a bounded wait (the
  sweep's 5 s) has to cancel again or give up. A second cancel will happen
  somewhere; the hang only needs one.

### Option C — translate the error back at the database layer

Wrap Coffer's session factory so that any exception raised while the task has a
cancel outstanding is re-raised as `CancelledError`.

- **Good:** one place covers every caller that reaches the database.
- **Bad:** only the database. The same swallowing happens with any other
  library whose cleanup raises (an HTTP client closing a stream, a subprocess
  pipe), and a session wrapper changes the type of every error on the request
  path too, where the request handler, not a loop, should decide.

### Option D — a loop asks its task, not the exception (chosen)

`application/runtime/cancellation.py` gains `stop_requested()`: whether the
running task has a cancel request outstanding (`Task.cancelling() > 0`). Every
handler that catches `Exception` and then carries on in a long-lived loop first
calls `raise_if_stopping(exc)`, which re-raises `CancelledError` (chained to
what it caught) when the answer is yes:

- the shared `WakeableLoop` (reconciler, attention watch, vault scanner,
  channel runtime, usage ingest, model proxy watchdog, MCP session reaper);
- `TaskSupervisor.spawn_restarting`, so a stop is not recorded as a crash and
  restarted;
- the reconciler's pass (a target that fails to plan, a repair that fails, an
  audit that fails after the undo) and the attention list's per-source isolation;
- the hand-written periodic loops that touch the database: sync, retention,
  memory sync, the knowledge sweep, the MCP invocation writer and the skill
  update check.

- **Good:** fixes the cause the hang needs (a loop outliving its stop) whatever
  library raised, without touching any error's type on the request path. Each
  guard is two lines, next to the handler it qualifies, and unit tests drive
  each shared loop with a run that turns its cancel into `RuntimeError("no
  active connection")`; before the change those tests hung exactly like CI.
- **Bad:** a new periodic loop has to remember the guard. Most loops are
  built on `WakeableLoop` or `spawn_restarting`, which carry it, so the
  remaining risk is a new hand-written loop.

## Decision

Option D. A background loop treats an outstanding cancel request as a stop,
whatever exception its run ended with; `raise_if_stopping(exc)` is how it asks.
Options A and B are rejected because the hang needs only one second cancel,
which Coffer cannot rule out. Option C is rejected because the swallowing is a
property of the loop, not of the database.

## Consequences

- The integration tier's teardown no longer waits on a worker that swallowed
  its stop; the flaky 300 s timeouts go away with it.
- The daemon's own shutdown, which ends in the same final sweep, no longer has
  a way to hang on a worker caught mid-query.
- A run that genuinely fails while nothing is stopping it is still logged and
  the loop carries on, as before.
- A new hand-written loop with an `except Exception` that carries on should
  call `raise_if_stopping(exc)`; putting it on `WakeableLoop` or `spawn_restarting`
  gets that for free.
