## Why

An idle daemon averaged about 1.8 % CPU on the owner's laptop. A count of what
wakes it while nothing happens found about 43 wake-ups a second, and about 40
of them came from two places nobody had listed:

- **The MCP invocation writer polled its queue every 50 ms**
  (`asyncio.wait_for(queue.get(), timeout=0.05)`), about 20 wake-ups a second,
  forever, although it commits greedily the moment a row arrives anyway.
- **The vault file watch ran watchfiles with its defaults.** Its native loop
  takes the GIL every 50 ms (`step`) to check for a stop, about 20 times a
  second, and re-enters a worker thread every 5 s (`rust_timeout`) for no
  event.

And every periodic reconcile pass (once a minute) told its listeners, even when
it wrote nothing: the model proxy state was rebuilt (a token decrypt per agent,
an attest challenge and a state push while the proxy runs) and the attention
list recomputed, every minute, for no change.

This is the first of three steps of the background-work plan the owner chose
(T-1, plan B): fix the hot spots first and measure again, then give every worker
one wakeable loop with a status line, then move the workers onto it.

## What Changes

- The invocation writer sleeps on its queue with no timeout. `stop()` queues a
  marker behind the last row, so shutdown still drains every row and returns at
  once. The `flush_interval_seconds` knob goes, since nothing waits on it.
- The vault watch runs with a 500 ms step and a 60 s native timeout: two
  wake-ups a second instead of twenty, a thread hop a minute instead of every
  5 s, and an edit is still settled after the scanner's 1 s of quiet.
- A **periodic** reconcile pass that wrote nothing, failed no new target and
  left the same differences open tells no pass listener. Every other writing
  pass (boot, hinted, change, import, manual, a feature switch, or a periodic
  pass that found something) still does, so the model proxy is pushed and the
  attention list recomputed whenever something could have changed.

## Impact

- Spec `daemon`, "Supervise the model proxy from the daemon": the push follows
  every reconcile pass that could have changed what the proxy serves, not every
  pass.
- Code: `infrastructure/mcp/invocation_writer.py`,
  `infrastructure/vault/scanner.py`, `application/reconcile/reconciler.py`.
- Docs: `docs-site/architecture/model-proxy.md`, `reconciler.md`, `daemon.md`
  (en + zh).
