## Why

The daemon started its background work with about fifty bare
`asyncio.create_task` calls. A task that raised died quietly — `asyncio`
reports an exception nobody retrieved only when the task is garbage-collected,
if ever — so a Telegram poll loop that hit a bug stopped receiving messages and
said nothing. Nothing measured the event loop either, so one synchronous call
blocking it stalled every request, channel and turn at once and showed up only
as "everything is slow".

The three records a person reads to answer "what happened" could not be
joined: the daemon log carried a `trace_id`, the MCP invocation log only the
MCP session id, and the audit row neither. Lining them up meant guessing from
timestamps.

## What Changes

- daemon: new requirement "Supervise every background task the daemon
  starts". Background work runs through one supervisor that names each task,
  writes a `runtime.task.crashed` line with the task's name and the exception
  when one raises, restarts a task only when its owner asks, and cancels what
  is still running at shutdown. Each channel adapter's inbound loop is
  restarted on its own after a crash; SeaTalk's websocket keeps its listen
  thread. A lint gate (`scripts/check_bare_tasks.py`) refuses a new bare
  `create_task` outside an explicit allow-list.
- daemon: new requirement "Report event-loop lag and background task crashes on
  the status". `GET /api/v1/daemon/status` gains a `runtime` block — the loop
  lag's p99 and maximum over a five-minute window, the tasks running, the crash
  count and the last crash (task and exception class) — and
  `coffer daemon status` prints it.
- resource-framework: new requirement "Correlate the audit log, the MCP
  invocation log and the daemon log by one trace id". Audit rows carry the
  request's or turn's `trace_id` and a turn's `conversation_id` and `turn_id`;
  MCP invocations carry the `trace_id` beside the session id; log lines carry
  all of them. `GET /api/v1/audit`, `GET /api/v1/mcp/invocations` and
  `GET /api/v1/daemon/logs` filter by `trace_id`, `coffer log audit|mcp|daemon`
  take `--trace`, and the Activity drawer shows the id.
- `runs.db` migration 0137 adds the columns and their indexes.

## Impact

- Code: `application/runtime/` (supervisor, loop-lag probe, correlation ids),
  every background task site, the audit and invocation repositories and routes,
  the log formatter, the CLI log readers and `coffer daemon status`, the
  Activity drawer.
- Wire: the daemon, mcp-gateway and resource-framework contracts.
- ADR `background-work-runs-supervised-and-correlated` (Proposed).
