## Why

ADR `background-workers-wake-on-events` moves the daemon's background workers
off fixed polling: each sleeps until an event wakes it, with at most a long
fallback timer, and a worker nothing needs is parked with no timer at all. The
reconciler, the attention watch and the vault scanner each wrote that loop by
hand, three slightly different ways, and the status could not say what any of
them was doing: `tasks_by_name` shows that `reconciler` is alive, not whether
it is waiting, running or stuck, how long its last pass took, or when it will
run next. Once more workers move onto events, "is this one idle because
nothing happened, or because its wake-up was lost?" needs an answer that does
not mean reading `daemon.log`.

Comparable runtimes report the same thing per worker: systemd's
`systemctl list-timers` prints each timer's last and next run, Kubernetes
controllers expose per-controller reconcile counts and durations, and Sidekiq's
cron and Celery beat list each periodic job with its next run.

## What Changes

- One shared loop for a background worker (`application/runtime/wakeable.py`):
  woken by a poke, a burst of pokes settled into one run, an optional fallback
  timer, parked with no timer while there is no demand. A run that raises is
  logged under the worker's own event name and counted, and the loop carries
  on. The reconciler, the attention watch and the vault scanner move onto it
  with their timing and log lines unchanged.
- `GET /api/v1/daemon/status`'s `runtime` block gains **`workers`**: one row
  per worker on that loop with its name, how it is woken (`event`,
  `event+fallback`, `on-demand`), its state (`waiting`, `running`, `parked`),
  its runs and failures, when its last run started, how long it took and
  whether it ended without raising, and when its fallback timer runs it next.
- `coffer daemon status --workers` prints one line per worker.

## Impact

- Spec `daemon`: a new requirement for the worker rows on the status and the
  command line.
- Code: `application/runtime/` (new `wakeable.py`, `workers.py`), the
  reconciler, the attention watcher, the vault scanner, the daemon status
  schema and CLI.
- Docs: `docs-site/architecture/observability.md`, `daemon.md`, the CLI
  reference, and their `zh/` twins; ADR `background-workers-wake-on-events`.
- The status route and `--json` gain a field; nothing is removed.
