## MODIFIED Requirements

### Requirement: Report event-loop lag and background task crashes on the status
The daemon MUST sample how late its event loop wakes a periodic probe and keep
the samples for a rolling window, because a synchronous call that blocks the
loop stalls every request, channel and turn at once and is otherwise visible
only as general slowness. `GET /api/v1/daemon/status` MUST carry a `runtime`
block with the window's 99th-percentile and maximum lag in milliseconds (null
before the first sample), the number of samples and the window's length, the
number of supervised tasks running, those running tasks counted by name
(`tasks_by_name`, keyed by the part of each task's name before the first `:`),
the number of background task crashes since the daemon started, and the most
recent crash's task name, exception class, time and whether it was restarted.
The crash's exception message MUST NOT appear there, nor the part of a task's
name after the first `:` (a channel, a server, a chat) — the probe answers
without a token, and a message can carry what it failed on — only in
`daemon.log`. When the loop misses the probe's wake-up by more than 100 ms, the
daemon MUST log a `runtime.loop.stalled` line to `daemon.log` carrying the loop
thread's stack and the running task's name as they are while the loop is still
blocked, at most one such line per 10 seconds with a count of the ones held
back. `coffer daemon status` MUST print the lag and the task counts,
`--tasks` MUST add the counts by name, largest first, and `--json` MUST carry
the `runtime` block as the route answers it.

#### Scenario: the status reports loop lag and task crashes
- **GIVEN** a running daemon whose probe has taken a sample, and a supervised task that has crashed with `LookupError`
- **WHEN** `GET /api/v1/daemon/status` is called with no token
- **THEN** its `runtime` block carries the lag's p99 and maximum over a 300-second window, the tasks running and the crash count including that crash
- **AND** `last_crash` names the task and `LookupError`, and the exception's message is nowhere in the block

#### Scenario: the status counts running tasks by name
- **GIVEN** a running daemon with two supervised tasks named `test-parked:private-0` and `test-parked:private-1`
- **WHEN** `GET /api/v1/daemon/status` is called with no token
- **THEN** `runtime.tasks_by_name` counts `test-parked` as 2 and the lag probe's `loop-lag-probe` as 1
- **AND** `private-` appears nowhere in the block

#### Scenario: a stalled loop is logged with what blocked it
- **GIVEN** the lag probe running with its stall watch
- **WHEN** a task blocks the loop with a synchronous call for longer than the threshold
- **THEN** `daemon.log` gains a `runtime.loop.stalled` line naming that task and carrying a stack that contains the blocking call
- **AND** a loop that keeps up logs no such line, and repeated stalls inside the rate-limit window log one line

#### Scenario: the command line prints loop lag and task crashes
- **GIVEN** a running daemon whose probe has taken a sample
- **WHEN** the user runs `coffer daemon status`, and `coffer daemon status --json`
- **THEN** the first prints a `loop lag:` line with the p99 and maximum and the window, and a `tasks:` line with the running and crashed counts
- **AND** the second carries the route's `runtime` block

#### Scenario: the command line lists running tasks by name
- **GIVEN** a running daemon whose tasks count `seatalk-ws` 2, `turn` 2 and `reconciler` 1
- **WHEN** the user runs `coffer daemon status --tasks`
- **THEN** below the `tasks:` line it lists each name with its count, largest first and by name within a count
- **AND** without `--tasks` the names are not printed, and `--json` carries `tasks_by_name`
