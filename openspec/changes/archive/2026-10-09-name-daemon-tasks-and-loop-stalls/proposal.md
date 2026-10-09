## Why

Three small gaps in what the daemon tells about its own runtime, found while
reading a live daemon:

- **A loop stall had no culprit.** The status showed a 120 ms maximum loop lag
  on an idle daemon, but the lag probe measures a stall only after the loop
  wakes, when whatever blocked it has returned and left no trace. Finding the
  call meant guessing from the code.
- **The task count had no breakdown.** `coffer daemon status` printed
  `tasks: 48 running` and nothing could say which tasks those were, so a leak
  (sessions never reaped, a channel loop started twice) could not be told from
  normal load.
- **`daemon.json` carried a field nobody read.** `binary_path` was written and
  parsed, and three docs listed it, but no client used it; the identity check
  on a pid uses the process command line. A field that looks load-bearing and
  is not misleads readers into thinking it takes part in that check.

Comparable runtimes do the first two the same way: Node's
`--trace-event`/`blocked-at`, Python's `aiodebug` and asyncio debug mode's
`slow_callback_duration` name the slow callback, and Go's `/debug/pprof/goroutine`
groups goroutines by function so a leak shows as one growing line.

## What Changes

- A **stall watch** thread beside the event loop: when the loop misses the lag
  probe's wake-up by more than 100 ms, it logs `runtime.loop.stalled` to
  `daemon.log` with the loop thread's stack and the running task's name, taken
  while the loop is still blocked. Lines are rate-limited to one per 10 s, with
  a count of the ones held back.
- `GET /api/v1/daemon/status`'s `runtime` block gains **`tasks_by_name`**: the
  running supervised tasks counted by the part of their name before the first
  `:`. What follows the colon (a channel, a server, a chat id) never appears,
  since the route answers without a token. `coffer daemon status --tasks`
  prints the counts, largest first.
- **`binary_path` is removed from `daemon.json`**: no longer written or parsed,
  and gone from the data model and the docs. The installed-build acceptance
  harness takes the daemon's executable from the status route's `executable`,
  which already reports the same path.

## Impact

- Spec `daemon`: the status requirement gains the task counts and the stall
  line; `data-model.md` loses `binary_path`.
- Code: `application/runtime/` (new `stall_watch.py`, supervisor counts),
  daemon status schema and CLI, `infrastructure/daemon/pid_lock.py` and
  `bootstrap.py`, `e2e/installed/_common`.
- Docs: `docs-site/architecture/observability.md`, `daemon.md`,
  `guides/daemon.md`, `reference/filesystem.md`, the CLI reference, and their
  `zh/` twins.
- A CLI or shim older than this change reads a `daemon.json` without
  `binary_path` as "no daemon". No release has shipped `binary_path`, and an
  agent session started before the upgrade picks up the new shim when it is
  restarted.
