# Background Work Runs Supervised, and Every Record Carries One Correlation Id

**Status**: Accepted
**Date**: 2026-10-01
**Deciders**: Yuxing Wu
**Related**: [Channels Are Thin Transport Adapters Over One Shared Core, Supervised In-Daemon](channel-adapter-framework.md), [SeaTalk Inbound Is One Outbound WebSocket, Through an Operator-Supplied SDK](seatalk-websocket-inbound.md), [Telegram Inbound Is a Long Poll That Commits the Offset After Dispatch](telegram-long-polling.md), [The Daemon Is Resident: It Never Idles Out, and a Login Service Restarts Only a Crash](daemon-is-a-resident-login-service.md), [Evals: Opt-In Capture, Hand Curation, and a Deterministic Regression Gate](eval-capture-and-regression-gate.md), spec daemon "Supervise every background task the daemon starts", spec daemon "Report event-loop lag and background task crashes on the status", spec resource-framework "Correlate the audit log, the MCP invocation log and the daemon log by one trace id", change archive `openspec/changes/archive/2026-10-01-supervise-background-tasks-and-correlate-records/`

## Context

The daemon is one Python process on one `asyncio` event loop. Everything
long-lived in it is a task on that loop: each channel adapter's inbound loop (a
Telegram long poll, the loop that supervises a SeaTalk websocket), each chat or
channel turn and its renderer, the reconciler, and the periodic workers
(retention, curation, memory, sync, price refresh, usage). The 1.0 audit
counted about fifty `asyncio.create_task` / `ensure_future` calls starting them,
each owner keeping — or not keeping — its own reference.

Three things followed from that, all found in real use rather than in theory:

- **A crashed task was silent.** `asyncio` holds a task's exception until
  something retrieves it. For a fire-and-forget task nothing does, so the
  exception surfaced, at best, as "Task exception was never retrieved" on
  stderr when the task was garbage-collected — and an owner that kept the
  reference and never awaited it stopped even that. A Telegram poll loop that
  hit a bug outside its own retry ladder stopped receiving messages and said
  nothing; the channel still read "running".
- **A blocked loop was invisible.** One synchronous call on the loop thread — a
  large file walk, a subprocess wait, a slow commit — stalls every request,
  every channel and every turn at once. Nothing measured it, so it presented as
  "Coffer is slow" with no signal pointing at the loop.
- **The three records could not be joined.** The daemon log carried a
  `trace_id` per HTTP request (`X-Coffer-Trace`), the MCP invocation log only
  the MCP session id, and the audit log neither. "What else did this request
  do?" — the first question when a tool call fails — meant lining rows up by
  timestamp across a SQLite table and a JSON file.

Two constraints bound the answer. The SeaTalk SDK is synchronous: its
`listen()` blocks for the life of the connection and must stay on a thread the
daemon owns (see the SeaTalk ADR). And Coffer runs on one machine for one
person, so a tracing or metrics backend is a dependency with no second reader.

## Options Considered

### Option A — one process-wide supervisor, a loop-lag probe, and correlation ids in a context variable (chosen)

- **Supervision.** `application/runtime/supervisor.py` is the one way to start
  background work. `spawn(coro, name=…)` names the task and adds a done
  callback that, when the task raised, writes one `runtime.task.crashed` line
  (task name, exception class, traceback) and counts it.
  `spawn_restarting(factory, name=…)` re-runs a long-lived loop after a crash,
  backing off from 1 s doubling to 60 s; a clean return ends it. The shutdown
  sequence stops each owner's work in its own order first, then the supervisor
  cancels what is left, bounded. The supervisor is process-wide because most
  tasks start deep inside a kind with no composition-root handle, and the
  crash count is the daemon's, not a kind's.
- **Per-adapter crash isolation.** Each channel adapter's inbound loop is its
  own restarting task — `telegram-poll:<channel>`, `seatalk-ws:<channel>` — so
  one adapter's crash restarts that loop and nothing else. The channel runtime
  that reconciles adapters is itself a restarting task, and keeps its existing
  30-second latch for an adapter that fails to *start*. SeaTalk's blocking
  `listen()` keeps its thread; what is supervised is the asyncio loop that owns
  the thread and reconnects it.
- **A gate.** `scripts/check_bare_tasks.py` (in `make lint`) counts
  `create_task` / `ensure_future` calls per file and fails when a file exceeds
  its allow-list entry. The list holds only structured concurrency — the two
  sides of an `asyncio.wait` race, a shielded write, a per-request pump, each
  awaited or cancelled before the function returns — with the reason written
  beside each file, and a stale (too generous) entry fails too.
- **Loop lag.** `application/runtime/loop_lag.py` sleeps 0.5 s at a time and
  records how late the loop woke it, keeping 600 samples (five minutes).
  `GET /api/v1/daemon/status` reports the window's p99 and maximum beside the
  running-task and crash counts and the last crash's task and exception
  class; `coffer daemon status` prints them. The status answers without a
  token, so the exception's message stays in `daemon.log`.
- **Correlation ids.** `application/runtime/correlation.py` holds the current
  unit of work's ids in one `ContextVar`: `trace_id` (the HTTP request's, or a
  turn's own), `session_id` inside an `/mcp` call, `conversation_id` and
  `turn_id` inside a turn. The log formatter stamps them on every line, the
  audit service on every row, the gateway on every invocation. `asyncio`
  copies the context into each task it creates, so a turn bound around its
  spawn hands its ids to its renderer with no parameter threaded through. Each
  of the three records filters by `trace_id` over REST and with `--trace` on
  `coffer log`, and the Activity drawer shows it. Migration 0137 adds the
  columns; older rows stay NULL rather than receive an invented id.

It costs one small package and one import at each task site, plus a list to
keep honest. It wins because each piece answers one of the three incidents
directly, with the standard library alone.

### Option B — keep bare tasks, install a loop exception handler

`loop.set_exception_handler` sees "exception was never retrieved" and could
log it in Coffer's format. It changes no call site. It loses because the handler
fires only when the task is garbage-collected — minutes later, or never when
the owner holds a reference — so the crash is still not reported when it
happens, and nothing can restart the loop that died or count the crash for the
status.

### Option C — `asyncio.TaskGroup` per owner

Structured concurrency: each owner opens a `TaskGroup`, and a failing child
propagates. It is the right shape for work that must finish together, and the
allow-listed races already follow it. It loses for background work because a
TaskGroup cancels every sibling when one child fails — exactly the opposite of
"one adapter's crash touches no other channel" — and because most of these
tasks have no enclosing scope to hold the group: a turn outlives the request
that started it, and a worker lives for the daemon's life.

### Option D — a third-party job library (`aiojobs`, anyio task groups)

`aiojobs` offers a scheduler with named jobs and a close; anyio offers task
groups over asyncio. Either would replace a small module with a dependency.
They lose on fit: `aiojobs` has no restart policy and reports failures through
an exception handler (Option B's timing problem), and anyio's task groups have
Option C's cancel-siblings semantics. Coffer's own code deliberately imports
`asyncio`, never `anyio` (`.agents/stack.md`).

### Option E — restart a crashed adapter through the channel runtime

The channel runtime already stops and starts adapters when their config
changes; it could notice a dead inbound task and rebuild the whole adapter. It
reuses one mechanism. It loses because a rebuild re-materialises secrets and,
for SeaTalk, re-registers the websocket — a restart the platform sees as a new
connection and that touches the secret store — to recover from a bug in a loop
that only needed running again. The runtime keeps the job it does well
(reconciling wanted against running), and the loop's restart stays local.

### Option F — OpenTelemetry tracing and metrics

Spans would carry the correlation, and a histogram the loop lag. It is the
industry answer for a fleet. It loses here because it needs an exporter and a
backend for a single-user local process whose readers are `coffer log`, the
Activity page and an agent with `grep`; the one idea worth taking from it — one
id carried across every record of a request — is what Option A keeps.

### Option G — pass correlation ids as parameters

Threading `trace_id` and `turn_id` through every call that might log or audit
is explicit and testable. It loses on reach: the audit service is called from
dozens of places in nine kinds, log lines from hundreds, and a parameter
missing at any one of them silently breaks the join. The context variable is
already how the HTTP trace id reached the log formatter; this extends the same
seam to the rows.

## Decision

The daemon's background work runs under one task supervisor: every task is
named, a crash is logged with that name and counted when it happens, only an
owner that asks is restarted (with a doubling backoff), and shutdown sweeps
what is left. Each channel adapter's inbound loop restarts on its own; the
SeaTalk SDK's blocking listener keeps its thread. A lint gate refuses a new bare
`create_task` outside the supervisor except for listed, reasoned structured
concurrency. An event-loop lag probe keeps a five-minute p99, reported with the
crash count on the status. One correlation id per request or turn — the trace
id, plus the MCP session and the turn's conversation and turn ids — rides a
context variable onto every log line, audit row and MCP invocation, and each
record filters by it.

Rules a future change must respect:

- Start background work with `spawn` or `spawn_restarting`, never a bare
  `create_task`; a task awaited in place goes on the gate's list with its
  reason.
- Restart only what its owner asked to restart; a one-off task that crashed
  stays gone.
- Never put a crash's exception message on the tokenless status route.
- A new record type that should be joinable stores `trace_id` from
  `correlation.current()`, never a parameter threaded by hand.

## Consequences

- A crashed task is a `runtime.task.crashed` line the moment it dies, and a
  number on `coffer daemon status`; a crashed Telegram or SeaTalk loop comes
  back by itself without touching the other channels.
- A blocked loop shows up as a p99 in the hundreds of milliseconds instead of
  as vague slowness.
- `coffer log audit|mcp|daemon --trace <id>` answers "what else did this
  request or turn do?" in three commands, and the Activity drawer names the id
  to ask with.
- Every background task site imports the supervisor, and the allow-list is one
  more file to keep level with the code — the gate fails a stale entry so it
  cannot drift silently.
- Enforced by `scripts/check_bare_tasks.py`, the `runtime` block of
  `GET /api/v1/daemon/status`, the correlation ids on the audit and invocation rows, and the specs named
  above.
