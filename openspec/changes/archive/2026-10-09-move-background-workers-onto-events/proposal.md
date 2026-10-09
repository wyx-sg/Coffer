## Why

ADR `background-workers-wake-on-events` step 3. After steps 1 and 2 an idle
daemon still woke on short timers for work that had nothing to do:

- The channel runtime re-read every channel every 2 seconds to notice an
  enable, a disable or an edit that the resource write had already announced.
- The model proxy watchdog woke every 5 seconds even while no agent was routed
  through the proxy and none was running, only to see that nothing was needed.
- The usage ingest listed the proxy's spool every 2 seconds whether or not a
  proxy was running to write it.
- The MCP session reaper woke every minute with no session open.

The events that matter already exist. Resource writes, including sync and hand
edits, are hinted. A secret stored or approved runs the approval callbacks.
Every change that could route an agent through the proxy is followed by a
state push. The proxy's supervisor knows whether a proxy runs.

## What Changes

- **The channel runtime** runs a pass on a resource write, on a secret stored
  or approved, and when a failed start's 30-second retry wait is over. With
  nothing waking it, it looks every 5 minutes, for a change no event
  announces. Switching a channel on, off or editing it therefore takes effect
  at once rather than within 2 seconds.
- **The model proxy watchdog** is on demand. While no proxy runs and none is
  needed, it parks with no timer, and the next state push wakes it. While a
  proxy runs, it still probes it every 5 seconds and restarts it after a crash.
- **The usage ingest** follows the proxy. While a proxy runs it empties the
  spool every 2 seconds. When the proxy stops, one more pass takes what it
  left, and then the ingest parks until a proxy runs again.
- **The MCP session reaper** parks while no session is open and wakes on the
  first session activity.
- All four report on `runtime.workers` (`channel-runtime`, `model-proxy`,
  `usage-ingest`, `mcp-session-reaper`).

The reconciler keeps its 60-second period. Lengthening it needs the agents'
config files to be watched, and that work is left to a later change.

## Impact

- Spec `daemon`: a new requirement for workers that wake on events and park
  without demand.
- Spec `channels`: "Report a channel that is starting…" now speaks of the next
  pass, which the write that switches a channel on brings forward.
- Code: `application/channel/runtime.py`, `channel_wiring.py`,
  `infrastructure/model_proxy/supervisor.py`, `application/usage/ingest.py`,
  `usage_wiring.py`, `kind_wiring.py`, `surfaces/http/mcp/session_registry.py`.
- Docs: `docs-site/architecture/daemon.md` and its `zh/` twin; ADR
  `background-workers-wake-on-events`.
