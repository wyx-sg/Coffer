# Daemon Detect-or-Spawn Pattern

**Status**: Accepted
**Date**: 2026-05-20 (revised 2026-05-30; see Revision history)
**Deciders**: Yuxing Wu
**Related**: spec `mcp-gateway` (FR-017, FR-018), [Session Subprocess Model](session-subprocess-model.md)

## Context

Coffer has multiple entry points that need a running daemon:

- `coffer-mcp-shim` — spawned by an MCP client (Claude Code, Codex) on every
  client startup.
- `coffer …` CLI — invoked ad hoc by the user.

The daemon must **outlive any single entry point**: the user expects the shim
from one MCP client not to die when another client's shim exits, and expects
a `coffer` CLI invocation to leave the daemon running after it returns.

The question is how the daemon gets started, how clients discover it, and what
owns its lifecycle.

## Decision

**Detect-or-spawn pattern with daemon-as-independent-process.**

- The daemon is an independent process bound to `127.0.0.1:<port>`. The port is
  **the user's fixed port when one is configured** in `~/.coffer/daemon-config.json`
  — bound exactly, never fallen back from — and otherwise is chosen at startup
  (default 8000; falls back to the next free port if taken; small bounded range).
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
- Because the daemon outlives its callers, a freshly-installed Coffer version
  can reuse an **older** detached daemon that's still listening — a silent
  version skew. Mitigated by **detection, not auto-update**: the daemon reports
  its package version (`coffer.__version__`) on `GET /api/v1/daemon/status`, and
  the CLI compares it against its own `coffer.__version__`. On mismatch
  `coffer daemon status` says the daemon is out of date and points at
  `coffer daemon restart`, and the daemon-served web UI's daemon-offline banner
  shows the same "daemon out of date — restart it" affordance; Coffer never
  auto-kills the running daemon.

**Operational follow-on**

- Upstream MCP subprocesses are reaped authoritatively when their connection
  closes or is evicted: each recorded PID (and its descendants — the upstream
  is typically a `uv`/`npx` wrapper over an interpreter grandchild) is
  SIGTERM/SIGKILLed if the SDK teardown left it alive. This is the primary
  guard against leaks accumulating on a long-lived daemon. The startup sweep
  over `~/.coffer/upstream-pids/` remains as a backstop for PIDs orphaned by a
  daemon *crash* (no clean shutdown).
- Stale **sibling daemons** are reaped when a fresh daemon wins the bind. A
  persistent daemon that stops answering `GET /api/v1/daemon/status` (wedged,
  mid-crash, or a spawn-race loser) is terminated by neither `release()` (which
  only guards `daemon.json`) nor the upstream sweep, so displaced daemons
  otherwise accumulate across app launches. On reaching serving — i.e. after
  `live_daemon()` found nobody live and we bound the port — the daemon reaps any
  other process running its own executable (`orphan_sweep.reap_stale_daemons`,
  excluding itself, its PyInstaller bootloader parent, and all ancestors).
  **Frozen builds only:** a source run's executable is the Python interpreter,
  which must not be matched. This is distinct from the version-skew case above —
  a *responding* older daemon is left for the user to restart, but a
  *non-responding* displaced one is cleaned up automatically.

## Alternatives Considered

**Manual daemon (user runs `coffer daemon start` before anything else).**
Rejected. Bad UX: forces the user to remember a setup step before every MCP
client interaction.

**An entry point owns the daemon (daemon dies when that entry point exits).**
Rejected. Then the shim breaks whenever the entry point that happened to start
the daemon exits. The point of detect-or-spawn is that every entry point is an
independent surface over the same long-lived state.

**No discovery file — fixed port + ambient token.** Rejected, and still
rejected: the token is minted per start and the pid is per process, so
discovery state has to be written somewhere regardless, and one file holding
all of it beats splitting it. Note what the 2026-09-12 revision does *not* do —
it does not remove the discovery file. `daemon.json` keeps carrying pid, port
and token exactly as before; only the *choice* of port gains an optional
user-set input, in a separate file that is configuration rather than state. The
two files are deliberately distinguishable at a glance: `daemon-config.json`
goes in and survives shutdown, `daemon.json` comes out and is unlinked on exit.

## Revision history

- **2026-09-12** — Optional fixed port. Port drift breaks the one thing a user
  is entitled to treat as stable — a browser bookmark to Coffer's own UI — and
  the range scan has no way to prefer the port the bookmark names. Self-eviction
  (below) was measured working: an orphan told to stand down by a newer
  `daemon.json` exits within one 30s check. It is nonetheless not a fix for
  drift, for two structural reasons. It converges a group of daemons on **one
  daemon**, not on **one port** — the survivor keeps whatever port it bound, so
  a drift to 8001 persists for that daemon's whole life even once 8000 frees up.
  And it only ever reads its own `HOME`'s `daemon.json`, while the port range is
  machine-wide: a daemon belonging to another vault — a live test run under a
  throwaway `HOME` is the common case, one was found holding 8001 on the
  maintainer's machine — occupies a port no eviction can reclaim, as does any
  unrelated process, and 8000 is heavily used.

  So the port becomes a setting. `~/.coffer/daemon-config.json` (`0600`,
  `{"version": 1, "port": <n>}`) is read by `bootstrap` *before* the bind. It is
  a file rather than a row because the port is chosen before the database is
  opened and before migrations run, and rather than an environment variable
  because the daemon is spawned detached by whichever surface first needs one
  and inherits that caller's environment — a shell profile reaches the user's
  own terminal and nothing else, least of all a GUI-launched agent's MCP shim.
  With a port configured the daemon binds exactly it and, if it cannot, refuses
  to start with the holding process named and the three resolving commands
  spelled out; falling back would reintroduce precisely the silent drift the
  setting exists to end. With none configured the range scan is untouched, and
  it stays the default: a machine whose 8000 is permanently taken must not be
  one where Coffer cannot start.

  Restart is the operation the fixed path has to get right, since it is how a
  port change is applied, so its bind sets `SO_REUSEADDR` (a `stop` immediately
  followed by a `start` otherwise fails on a port whose previously-accepted
  connections are still in `TIME_WAIT`) and retries briefly for the moment where
  the outgoing daemon has not quite let go. `coffer daemon restart` — which this
  ADR has referenced since 2026-06-13 without it ever existing — was added.

  `SO_REUSEADDR` is deliberately **not** set on the scan path, and the reason is
  worth recording because only CI found it. On Linux the option additionally
  permits two sockets to bind the same address and port whenever neither is
  `LISTEN`ing — and a Coffer daemon is bound-but-not-listening for its entire
  boot window, since uvicorn calls `listen` later on the fd it is handed.
  Setting it there dissolved CODE-041 outright: a second `acquire()` bound the
  very port the first was still holding, which is the case the CODE-041 test
  pins. macOS and the BSDs refuse that bind, so the local suite stayed green and
  the Linux CI run was the first thing to see it. The fixed path keeps the
  option because its bind is serialised by the spawn lock and its failure mode
  without it — a restart that cannot rebind — is certain rather than theoretical.

- **2026-09-09** — Orphan self-eviction. The spawn guard is one-sided: it probes
  only the single port `daemon.json` records, so it cannot see a daemon alive on
  any other port. Whenever that probe failed while a daemon was in fact running
  — `daemon.json` lost, or an already-serving daemon still finishing its warm-up
  and too slow to answer `/daemon/status` within the 2s probe timeout (measured
  at ~9s in the field) — the spawn bound the next free port and left the older
  daemon running forever holding its own. Nothing reclaimed it:
  `reap_stale_daemons` no-ops outside frozen builds (matching `python3`'s
  basename would target unrelated interpreters), so a run-from-source setup
  accumulated one orphan per restart. Observed in the wild: ten daemons holding
  all of 8000–8009, every one still serving, after which `bind_free_socket`
  could not start a daemon at all.

  Fixed from the other side, where no cross-process authority is needed. A
  serving daemon now re-reads `daemon.json` every 30s and, if it names a
  **different, live** Coffer daemon, shuts itself down
  (`bootstrap.superseded_by` → `entry._evict_when_superseded`). The conditions
  are deliberately narrow — an absent file never evicts anyone (deleting
  `daemon.json` must not take the healthy daemon down), a malformed one is no
  evidence, and a recorded pid that is dead or not a Coffer daemon means we are
  still the only daemon alive. A group of daemons therefore converges on the one
  `daemon.json` names, while a lone daemon with a missing or stale discovery
  file keeps serving. The liveness probe timeout also went 2s → 15s so a
  serving-but-busy daemon stops reading as absent; a stale `daemon.json` costs
  nothing there, since a dead port refuses the connection at once. The pid check
  both `daemon stop` and the new evictor need moved out of the CLI into
  `pid_lock.pid_is_coffer_daemon` (infrastructure cannot import surfaces).

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
  version on `GET /api/v1/daemon/status`, and the CLI (`coffer daemon status`)
  and the daemon-served web UI surface a manual "daemon out of date — restart
  it" affordance (`coffer daemon restart`) when a reused detached daemon's
  version differs from the caller's expected version. Detection + manual
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
  before sending `SIGTERM` (a recycled PID is no longer signalled). The
  detect-or-spawn liveness check switched from a bare TCP connect to an
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
