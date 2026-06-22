# ADR-006: Daemon Detect-or-Spawn Pattern

**Status**: Accepted
**Date**: 2026-05-20 (revised 2026-05-30; see Revision history)
**Deciders**: Yuxing Wu
**Related**: spec `001-mcp-gateway` (FR-017, FR-018), [ADR-005](ADR-005-session-subprocess-model.md)

## Context

Coffer has multiple entry points that need a running daemon:

- `coffer-mcp-shim` — spawned by an MCP client (Claude Code, Cursor) on every
  client startup.
- `coffer …` CLI — invoked ad hoc by the user.

The daemon must **outlive any single entry point**: the user expects the shim
from one MCP client not to die when another client's shim exits, and expects
a `coffer` CLI invocation to leave the daemon running after it returns.

The question is how the daemon gets started, how clients discover it, and what
owns its lifecycle.

## Decision

**Detect-or-spawn pattern with daemon-as-independent-process.**

- The daemon is an independent process bound to `127.0.0.1:<port>`, where
  `<port>` is chosen at startup (default 8000; falls back to the next free
  port if taken; small bounded range).
- On startup, the daemon writes `~/.coffer/daemon.json` (mode `0600`) with
  `{pid, port, token, started_at}`.
- The shim and the CLI both use the same `detect-or-spawn` helper:
  1. Read `~/.coffer/daemon.json`.
  2. If the file exists and the PID is alive, connect.
  3. Otherwise, spawn `coffer-daemon` as a detached process (stdio
     redirected to `~/.coffer/logs/daemon.log`), wait briefly for
     `daemon.json` to appear, then connect.
- The daemon does not auto-shutdown. It exits only on explicit
  `coffer daemon stop` or system shutdown.
- All clients carry the token from `daemon.json` in an `X-Coffer-Token` header
  on every request.

## Consequences

**Positive**

- Any entry point bootstraps the daemon — the user never sees "no daemon
  running" friction.
- The daemon survives the exit of whichever entry point started it. A shim-based
  MCP client keeps working after an unrelated `coffer` command returns, and one
  client's shim exiting does not take the daemon down for others.
- No privileged install is required. Setup is "run any `coffer` command once".
- A single discovery file keeps clients in sync with port changes — if 8000
  was busy and the daemon picked 8001, every client reads the same answer.

**Negative**

- "Who owns the daemon" is implicit (whoever first detected absence). Cleanup
  responsibility on the bootstrapper is mitigated by daemon not exiting on
  bootstrapper exit.
- Race condition possible if two clients detect absence and spawn
  simultaneously. Mitigated by an exclusive `flock` on `~/.coffer/daemon.lock`
  held across the freshly-spawned daemon's whole probe+bind+write critical
  section **and on past the bind, until the daemon is actually serving HTTP**
  (`bootstrap.acquire_or_existing`): under the lock it probes `live_daemon()`
  and binds a port + writes `daemon.json` only if none is live, then keeps the
  lock held — `acquire_or_existing` returns a `release` callable that the
  daemon entrypoint invokes only once uvicorn reports it is serving
  (`Server.started`). This is what makes the serialisation airtight: because
  `live_daemon()` confirms liveness with an HTTP `GET /api/v1/daemon/status`
  probe (not a bare port check), a port that is bound but not yet serving reads
  as **not** live. Had the lock dropped the instant `daemon.json` was written,
  a racing spawn could wake in that sub-second boot window, probe the
  not-yet-serving winner, get `None`, and bind a second port — orphaning the
  winner. Holding the lock until serving means the loser instead blocks on the
  lock until the winner answers `/daemon/status`, then observes it and exits
  cleanly. On shutdown the daemon's `release()` only unlinks `daemon.json` when
  it still records its own PID, so an orphaned daemon can never delete the live
  one's discovery file. (On Windows, which lacks `fcntl`, the lock degrades to
  a no-op and the `live_daemon()` refusal plus the atomic `os.replace` remain
  the guard.)
- Auto-spawn of a long-lived process from a child entry point (the shim) is
  unusual — users on Windows in particular may see a brief command window.
  Mitigated by detaching with `subprocess.CREATE_NO_WINDOW` on Windows and
  `os.setsid()` on POSIX.
- Because the daemon outlives the app, a freshly-installed app version can
  reuse an **older** detached daemon that's still listening — a silent version
  skew. Mitigated by **detection, not auto-update**: the daemon reports its
  package version (`coffer.__version__`) on `GET /api/v1/daemon/status`, and
  the desktop app compares it against the version this build expects (the Tauri
  `daemon_version_matches` command, sourced from `CARGO_PKG_VERSION`). On
  mismatch the existing daemon-offline banner shows a "daemon out of date —
  restart it" affordance reusing the manual restart path; Coffer never
  auto-kills the running daemon.

**Operational follow-on**

- Upstream MCP subprocesses are reaped authoritatively when their connection
  closes or is evicted: each recorded PID (and its descendants — the upstream
  is typically a `uv`/`npx` wrapper over an interpreter grandchild) is
  SIGTERM/SIGKILLed if the SDK teardown left it alive. This is the primary
  guard against leaks accumulating on a long-lived daemon. The startup sweep
  over `~/.coffer/upstream-pids/` remains as a backstop for PIDs orphaned by a
  daemon *crash* (no clean shutdown).

## Alternatives Considered

**Manual daemon (user runs `coffer daemon start` before anything else).**
Rejected. Bad UX: forces the user to remember a setup step before every MCP
client interaction.

**An entry point owns the daemon (daemon dies when that entry point exits).**
Rejected. Then the shim breaks whenever the entry point that happened to start
the daemon exits. The point of detect-or-spawn is that every entry point is an
independent surface over the same long-lived state.

**No discovery file — fixed port + ambient token.** Rejected. Port conflicts
on developer machines (8000 is heavily used) and shared-secret rotation would
both require either a configuration file or a discovery file. Choosing one
file with everything in it is simpler than splitting state.

## Revision history

- **2026-05-20** — Initial decision: detect-or-spawn pattern with daemon as
  independent process; shim and CLI both use the same helper; daemon writes
  `~/.coffer/daemon.json` on startup.
- **2026-05-30** — Implementation update: the `coffer` CLI now implements
  detect-or-spawn end-to-end. Previously the CLI would error and instruct the
  user to run `coffer daemon start` manually — a deviation from this ADR's
  stated intent that has now been corrected. Additionally, spawn is
  **frozen-aware**: when running as a PyInstaller binary (i.e.
  `sys.frozen is True`), the shim and CLI spawn the co-located `coffer-daemon`
  binary via `coffer.infrastructure.daemon.spawn.daemon_spawn_command()` rather
  than falling back to `python -m coffer_daemon`. This ensures the correct
  binary is used regardless of whether Coffer was installed from a prebuilt
  release archive or from a source checkout.
- **2026-06-13** — Version-skew detection: the daemon now reports its package
  version on `GET /api/v1/daemon/status`, and the desktop app surfaces a manual
  "daemon out of date — restart it" banner when a reused detached daemon's
  version differs from the app build's expected version. Detection + manual
  restart only; no auto-update, no auto-kill.
- **2026-06-13** — Spawn-race hardening (the `flock` this ADR always
  documented, now actually implemented). The freshly-spawned daemon's
  probe+bind+write now runs under an exclusive `flock` on
  `~/.coffer/daemon.lock` (`bootstrap.acquire_or_existing`), closing the
  check-then-act gap in which two near-simultaneous auto-spawns each bound a
  port and the loser's `os.replace` orphaned the winner. `release()` became
  PID-checked — it unlinks `daemon.json` only when the file still records its
  own PID, so an orphan's exit can't delete the live daemon's discovery file.
  `coffer daemon start` now keys off `live_daemon()` (a real status probe) so a
  stale `daemon.json` triggers a respawn instead of a false "already running";
  `coffer daemon stop` cmdline-verifies the recorded PID is a Coffer daemon
  before sending `SIGTERM` (a recycled PID is no longer signalled). The desktop
  app's detect-or-spawn liveness check switched from a bare TCP connect to an
  HTTP `GET /api/v1/daemon/status` 200 probe, so a port-squatter on a crashed
  daemon's recorded port no longer false-positives as a live daemon.
- **2026-06-22** — Shim restart-recovery. A long-lived `coffer-mcp-shim`
  resolved the daemon's port + token **once at startup** and pinned to them for
  its whole life. When the daemon was restarted on a different port (8000 was
  busy → it picked 8001, or vice versa), every existing shim kept POSTing to the
  dead port, returning `httpx.ConnectError: All connection attempts failed` for
  every tool call and spinning its SSE reconnect loop forever — the client (e.g.
  Codex) surfaced this as a per-tool "connection error" that looked like an
  upstream/URL misconfiguration but was purely the stale shim↔daemon endpoint.
  Fix: on a POST connect failure the shim now re-reads `daemon.json` once
  (`_Bridge._recover`); if a *live* daemon is found at a **different** endpoint
  it rebinds the shared httpx client's `base_url` + `X-Coffer-Token`, drops the
  defunct `Mcp-Session-Id`, replays the cached `initialize` handshake to
  establish a fresh session on the new daemon, and retries the call once. A
  same-endpoint blip stays a transient (normal backoff); a fully-down daemon
  still surfaces a JSON-RPC error (a fresh shim spawn is that path). The shared
  client rebind also steers the SSE reconnect loop onto the new daemon.
- **2026-06-13** — Boot-window close. The spawn `flock` is now held past the
  `daemon.json` write, until the daemon is actually serving HTTP:
  `acquire_or_existing` returns a `release` callable that the entrypoint
  invokes only once uvicorn reports `Server.started`. Previously the lock
  dropped the moment `daemon.json` was written, leaving a sub-second window in
  which a racing auto-spawn probed the bound-but-not-yet-serving port, got
  `None` from `live_daemon()`, and bound a second port — orphaning the winner.
  The concurrency test was corrected to drive a real bound-but-not-serving
  socket (and tie lock-release to *serving*) instead of treating
  "`daemon.json` exists" as liveness, which had masked the window.
