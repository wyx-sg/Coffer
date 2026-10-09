## ADDED Requirements

### Requirement: Report each background worker's schedule on the status
A background worker that sleeps until an event wakes it, with or without a
fallback timer, MUST report what it is doing, because a worker idle for lack of
events and one whose wake-up was lost otherwise look the same.
`GET /api/v1/daemon/status`'s `runtime` block MUST carry `workers`: one row per
such worker, by name, with how it is woken (`event` — only by an event;
`event+fallback` — by an event or a fallback timer; `on-demand` — parked with
no timer while nothing needs it), its state (`waiting`, `running` or `parked`),
its runs since it started and how many of them raised, when its last run
started, how long it took and whether it ended without raising, and when its
worker runs next: its fallback's deadline, or the end of the settle once an
event has woken it (null while it runs, is parked, or waits for an event only). A worker's name MUST be a fixed string, never a channel, server
or chat, since the route answers without a token. A run that raises MUST be
logged to `daemon.log` and counted, and the worker MUST carry on.
`coffer daemon status --workers` MUST print one line per worker with the same
facts, and `--json` MUST carry `workers` as the route answers it.

#### Scenario: the status lists each background worker
- **GIVEN** a running daemon
- **WHEN** `GET /api/v1/daemon/status` is called with no token
- **THEN** `runtime.workers` lists `reconciler`, `attention-watch` and `vault-scanner`
- **AND** the reconciler is woken by `event+fallback`, has no failures, and while it waits carries when its fallback runs next

#### Scenario: the command line lists each worker's schedule
- **GIVEN** a running daemon with a waiting `reconciler` whose last run took 12.5 ms and whose fallback runs in two minutes, and a parked on-demand `usage-ingest`
- **WHEN** the user runs `coffer daemon status --workers`
- **THEN** below a `workers:` line it prints each worker with its mode, state and runs, the reconciler's last run and `next in` about 120 seconds, and the parked worker with no next run
- **AND** without `--workers` the workers are not printed, and `--json` carries `workers`
