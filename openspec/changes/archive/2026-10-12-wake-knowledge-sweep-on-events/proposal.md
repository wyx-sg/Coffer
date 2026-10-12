## Why

The knowledge sweep was the last background worker on a fixed short timer: it
woke every 60 seconds on every machine whether or not a file under `knowledge/`
had changed. The other workers already wake on the event that gives them work
and fall back rarely (ADR background-workers-wake-on-events), and an idle daemon
that wakes every minute for nothing costs battery.

## What Changes

- **The knowledge sweep wakes on file events.** It borrows the vault scanner's
  one file watch: an event under `knowledge/` pokes it, a burst settles into a
  single run, and switching the `knowledge` feature on brings a run forward.
  Without any event it runs every 10 minutes, to catch an event the watch lost.
- **A loose document still inside its quiet minute is revisited.** The sweep
  schedules one more run for when that minute is over, since no file event
  announces the passing of time.
- **`knowledge-sweep` is listed on `runtime.workers`** like the other wakeable
  workers.

A file dropped into an inbox is still adopted within seconds, now by the event
instead of the timer.

## Impact

- Capabilities: `daemon` (the event-wake requirement gains the sweep),
  `knowledge` (the sweep requirement no longer says "recurring timer").
- Code: `knowledge_sweep_wiring.py`, `scanner.py` (a subtree listener on the
  existing watch), `background_workers.py`, `app.py`.
