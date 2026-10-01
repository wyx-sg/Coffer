## ADDED Requirements

### Requirement: Supervise every background task the daemon starts
Work the daemon starts to run beside the call that started it — a channel
adapter's inbound loop, a channel or chat turn, a periodic worker, a
fire-and-forget write — MUST run under one task supervisor rather than as a
bare `asyncio` task, because a bare task that raises dies silently: the
exception surfaces only if something later retrieves it. The supervisor MUST
give every task a name, and when a task ends by raising it MUST write one
`runtime.task.crashed` line to `daemon.log` carrying the task's name and the
exception with its traceback at that moment, and count the crash. A task MUST
be restarted after a crash only when its owner asked for that, with a backoff
that doubles from one second up to a cap; a clean return ends it. Each channel
adapter's inbound loop — a Telegram channel's long poll, a SeaTalk channel's
websocket supervisor — MUST be restarted on its own, so one adapter's crash
never stops or restarts another channel; the SeaTalk websocket's blocking
listen call keeps its own thread (spec
[channels/seatalk](../channels/seatalk/spec.md) "Receive every event over one
outbound websocket connection"). At shutdown, after every owner has stopped
its own work in the teardown's order, the supervisor MUST cancel whatever is
still running, bounded so a task that ignores cancellation cannot hold the
daemon up (see "Shut down through one graceful exit path"). A task the same
function awaits or cancels before it returns — the two sides of an
`asyncio.wait` race, a shielded write — is not background work; the lint gate
`scripts/check_bare_tasks.py`, run by `make lint`, MUST refuse any other bare
`create_task` or `ensure_future` outside the supervisor and MUST name each
allowed one, per file, with the reason it is awaited in place.

#### Scenario: a background task that crashes is logged with its name
- **GIVEN** a supervised task named `telegram-poll:family`
- **WHEN** it raises `RuntimeError`
- **THEN** `daemon.log` receives one `runtime.task.crashed` line naming `telegram-poll:family`, the exception class and its traceback
- **AND** the daemon's crash count goes up by one

#### Scenario: a crashed channel adapter restarts without touching the others
- **GIVEN** two running Telegram channels, each polling in its own supervised loop
- **WHEN** the first channel's loop raises an error its own retry ladder does not catch
- **THEN** the crash is logged under that channel's task name and its loop runs again after the backoff
- **AND** the second channel's loop keeps running and is never restarted

#### Scenario: shutdown cancels the background tasks still running
- **GIVEN** supervised tasks still running when the daemon shuts down
- **WHEN** the teardown reaches the supervisor's sweep
- **THEN** every one of them is cancelled, and none is counted as a crash

#### Scenario: a new bare background task fails the lint gate
- **GIVEN** a module under `backend/coffer/` that starts a task with `asyncio.create_task` and is not on the gate's allow-list
- **WHEN** `scripts/check_bare_tasks.py` runs
- **THEN** it fails and names the file, pointing at the supervisor's `spawn`
- **AND** an allow-list entry for more calls than a file makes fails too, as stale

### Requirement: Report event-loop lag and background task crashes on the status
The daemon MUST sample how late its event loop wakes a periodic probe and keep
the samples for a rolling window, because a synchronous call that blocks the
loop stalls every request, channel and turn at once and is otherwise visible
only as general slowness. `GET /api/v1/daemon/status` MUST carry a `runtime`
block with the window's 99th-percentile and maximum lag in milliseconds (null
before the first sample), the number of samples and the window's length, the
number of supervised tasks running, the number of background task crashes
since the daemon started, and the most recent crash's task name, exception
class, time and whether it was restarted. The crash's exception message MUST
NOT appear there — the probe answers without a token, and a message can carry
what it failed on — only in `daemon.log`. `coffer daemon status` MUST print the
lag and the task counts, and `--json` MUST carry the `runtime` block as the
route answers it.

#### Scenario: the status reports loop lag and task crashes
- **GIVEN** a running daemon whose probe has taken a sample, and a supervised task that has crashed with `LookupError`
- **WHEN** `GET /api/v1/daemon/status` is called with no token
- **THEN** its `runtime` block carries the lag's p99 and maximum over a 300-second window, the tasks running and the crash count including that crash
- **AND** `last_crash` names the task and `LookupError`, and the exception's message is nowhere in the block

#### Scenario: the command line prints loop lag and task crashes
- **GIVEN** a running daemon whose probe has taken a sample
- **WHEN** the user runs `coffer daemon status`, and `coffer daemon status --json`
- **THEN** the first prints a `loop lag:` line with the p99 and maximum and the window, and a `tasks:` line with the running and crashed counts
- **AND** the second carries the route's `runtime` block
