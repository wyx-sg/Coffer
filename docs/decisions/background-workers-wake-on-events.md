# Background Workers Wake on Events, Fall Back Rarely, and Stop When Nothing Needs Them

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [Background Work Runs Supervised, and Every Record Carries One Correlation Id](background-work-runs-supervised-and-correlated.md), [One Level-Triggered Reconciler Compares Parameters](one-level-triggered-reconciler-compares-parameters.md), [The Daemon Is Resident: It Never Idles Out, and a Login Service Restarts Only a Crash](daemon-is-a-resident-login-service.md), spec daemon "Supervise the model proxy from the daemon", change archive `openspec/changes/archive/2026-10-09-quiet-the-idle-daemon/`

## Context

The daemon is resident: it runs from login to logout, and most of that time
nothing is asking it for anything. On the owner's laptop an idle daemon averaged
about 1.8 % CPU (27.8 hours of uptime, 29.9 CPU minutes, measured 2026-10-07),
which a battery notices.

Every long-lived worker was started through the supervisor (see the related
ADR), but each chose its own schedule, and most chose a fixed sleep. Reading
every worker's loop (2026-10-09, `origin/main` at `cb0e215`) counted about 43
wake-ups a second on an idle daemon:

| Worker | Schedule while idle | Wake-ups/s |
| --- | --- | --- |
| MCP invocation writer | `wait_for(queue.get(), 0.05)` | ~20 |
| Vault file watch | watchfiles' native loop, `step` 50 ms (takes the GIL), thread re-entry every 5 s | ~20 |
| Loop-lag probe | 0.5 s | 2 |
| Channel runtime | 2 s: two full resource snapshots and a hash of each channel's secret, even with no channel | 0.5 |
| Usage ingest | 2 s: list the proxy's spool directory | 0.5 |
| Model proxy watchdog | 5 s; an HTTP health check while the proxy runs | 0.2 |
| Reconciler, attention watch, vault scanner, MCP session reaper, sync, skill updates, … | 30–60 s | ~0.1 |

The two largest were not where anyone had looked. Beyond the wake-ups, every
periodic reconcile pass rebuilt the model proxy's state (a token decrypt per
agent, an attest challenge and a push) and recomputed the attention list, once a
minute, whether the pass found anything or not. And the model proxy, once
started, ran and was health-checked every 5 s even after no agent was routed
through it any more.

The same "wait for a hint, settle, run, or run anyway after a period" loop had
been written three times by hand (the reconciler, the attention watch, the vault
scanner), and nothing reported when a worker last ran, how long it took or when
it would run next, so none of this was visible without reading the code.

## How comparable daemons do it

| System | Pattern | Fallback |
| --- | --- | --- |
| Kubernetes controller-runtime | Informers feed watch events into a rate-limited work queue; reconcile is level-triggered per key | `SyncPeriod` defaults to 10 hours; correctness comes from the events |
| Syncthing | Native file watcher, changes aggregated for 10 s, then a targeted scan | Full rescan every hour (it was 60 s before the watcher existed) |
| Docker Desktop | Resource Saver stops the VM after 5 minutes with no container and starts it on the next call | On demand |
| Tailscale | The control plane streams changes over a long poll; timers are avoided while idle to save mobile battery | Keepalives on the order of a minute |
| launchd / systemd | Socket activation starts a service on its first connection; timers are coalesced (`AccuracySec`, dispatch leeway) | On demand; about one-minute timer accuracy |
| VS Code | Native recursive watcher in a utility process, events coalesced over 50–75 ms, `.git/objects` excluded | No periodic rescan |

The common rule: events carry correctness, the fallback is minutes to hours and
exists only to catch a lost event, nothing fires more often than about once a
minute while idle, and work with no consumer does not run.

## Options Considered

### Option A — fix each worker in place

Each worker changes its own loop: block on its queue, subscribe to the hints it
needs, lengthen its period, stop itself when unused.

- **Good:** each change is small and local; no new abstraction.
- **Bad:** the event-plus-settle-plus-fallback loop, already written three
  times, would be written five or six more times, each with its own bugs around
  cancellation and missed wake-ups. Reporting each worker's last run, duration
  and next run on `coffer daemon status` would need the same bookkeeping added to
  every worker separately, and a new worker would still default to
  `while True: sleep(n)`.

### Option B — one wakeable loop and a worker registry (chosen)

`application/runtime/` gains a `WakeableLoop`: a named loop that runs one pass
when poked (after a short settle), when its fallback period elapses, or never
while its demand is off (`set_demand(False)` parks it with no timer at all). A
`WorkerRegistry` records, for every worker, its mode, its last start, duration
and outcome, and the deadline it sleeps toward; `GET /api/v1/daemon/status` and
`coffer daemon status` report them. The three hand-written loops and the plain
`sleep` loops move onto it, each classified as one of:

- **event + long fallback** (reconciler, attention watch, vault scanner, channel
  runtime, orphan evictor): woken by the hints and file events that already
  exist, with a fallback of 5–15 minutes;
- **on demand** (model proxy supervisor, usage ingest, price refresh, sync,
  skill updates, MCP session reaper): parked while nothing needs them, for
  example while no agent is routed through the model proxy;
- **purely event-driven** (the invocation writer): it waits on its queue.

- **Good:** one implementation of the hard part (cancellation, coalescing
  pokes, a missed deadline); the status lines come with it; a new worker is
  event-driven by default because that is what the loop offers.
- **Bad:** the reconciler, attention and vault-scanner loops are stable and
  tested, and moving them means re-proving them; one more layer to read.

### Option C — one central scheduler

A single task owns a timer wheel and wakes every worker, coalescing nearby
deadlines the way launchd's leeway does.

- **Good:** timer coalescing; one place that knows every deadline.
- **Bad:** most Coffer workers should be woken by events, not timers, so
  coalescing saves little. A central scheduler also lets one slow pass delay
  every other worker, and it cuts across the supervision model the related ADR
  chose, where each worker is its own supervised task and a crash restarts only
  that worker.

## Decision

Option B, in three steps so each can be measured:

1. **Hot spots** (done first): the invocation writer blocks on its queue and
   `stop()` wakes it with a marker; the vault watch runs with a 500 ms step and
   a 60 s native timeout; a periodic reconcile pass that wrote nothing, failed
   no new target and left the same differences open tells no pass listener, so
   the proxy push and attention recompute follow passes that could have changed
   something. Re-measure the idle daemon after this step.
2. **The loop and the registry**, with each worker's mode, last run, duration
   and next run on the status (`runtime.workers`, `coffer daemon status
   --workers`; change `report-background-worker-schedules`). The reconciler,
   attention watch and vault scanner move onto the loop in this step with their
   periods unchanged, since they were the three hand-written copies of it.
3. **Moving the workers**, with the model proxy started when the first agent is
   routed through it and drained and stopped when the last one leaves, usage
   ingest gated on the proxy and woken by it, the channel runtime woken by
   channel and agent hints, and the reconciler's period lengthened once the
   agent config files it compares are watched.

Knowledge and memory workers (knowledge sweep, memory aggregate, distil, sync)
are being redesigned separately and are not moved here.

## Consequences

- An idle daemon should wake a few times a second at most after step 1 (the
  lag probe and the file watch), and close to never after step 3.
- The model proxy's state is no longer refreshed every minute by the
  reconciler. It is still pushed on every pass that wrote something or was
  brought forward by a hint, on every token change and secret approval, and by
  the supervisor's own recheck, so a key rotation or a new agent reaches it as
  before.
- Shutting down waits up to one watch step (500 ms) for the native file watch
  to notice the stop, where it used to wait up to 50 ms.
- Steps 2 and 3 change the reconciler's period and the model proxy's lifecycle;
  their spec deltas and the reconciler ADR's period rationale change with them.
