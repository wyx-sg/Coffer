# ADR-006: Daemon Detect-or-Spawn Pattern

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: spec `001-mcp-gateway` (FR-017, FR-018), [ADR-005](ADR-005-session-subprocess-model.md), [ADR-007](ADR-007-distribution-pyinstaller-tauri-sidecar.md)

## Context

Coffer has multiple entry points that need a running daemon:

- The Tauri desktop app — opens, expects to manage daemon state.
- `coffer-mcp-shim` — spawned by an MCP client (Claude Code, Cursor) on every
  client startup.
- `coffer …` CLI — invoked ad hoc by the user.

The daemon must **outlive any single entry point**: the user expects to close
the desktop app's window without losing the ability for an MCP client to use
the shim, and expects the shim from one MCP client not to die when another
client's shim exits.

The question is how the daemon gets started, how clients discover it, and what
owns its lifecycle.

## Decision

**Detect-or-spawn pattern with daemon-as-independent-process.**

- The daemon is an independent process bound to `127.0.0.1:<port>`, where
  `<port>` is chosen at startup (default 8000; falls back to the next free
  port if taken; small bounded range).
- On startup, the daemon writes `~/.coffer/daemon.json` (mode `0600`) with
  `{pid, port, token, started_at}`.
- The Tauri app, the shim, and the CLI all use the same `detect-or-spawn`
  helper:
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
- The daemon survives Tauri-window close. Close-to-tray works (window hides,
  daemon stays); shim-based MCP clients continue to work even when no GUI is
  open.
- No privileged install is required. Setup is "open the app once" or
  "run any `coffer` command once".
- A single discovery file keeps clients in sync with port changes — if 8000
  was busy and the daemon picked 8001, every client reads the same answer.

**Negative**

- "Who owns the daemon" is implicit (whoever first detected absence). Cleanup
  responsibility on the bootstrapper is mitigated by daemon not exiting on
  bootstrapper exit.
- Race condition possible if two clients detect absence and spawn
  simultaneously. Mitigated by `flock` on `daemon.json` during write and by
  the daemon refusing to start if a valid `daemon.json` already exists with a
  live PID.
- Auto-spawn of a long-lived process from a child entry point (the shim) is
  unusual — users on Windows in particular may see a brief command window.
  Mitigated by detaching with `subprocess.CREATE_NO_WINDOW` on Windows and
  `os.setsid()` on POSIX.

**Operational follow-on**

- Orphaned upstream MCP subprocesses on daemon crash are cleaned up at next
  daemon startup using `~/.coffer/upstream-pids/`.
- A later spec may add an opt-in `coffer daemon install --system` for users
  who want launchd / systemd / Windows service supervision; that is a strict
  superset of this ADR.

## Alternatives Considered

**Manual daemon (user runs `coffer daemon start` before anything else).**
Rejected. Bad UX: forces the user to remember a setup step before every MCP
client interaction. Defeats the desktop-app promise.

**Tauri owns the daemon (daemon dies on Tauri quit).** Rejected. Then the shim
breaks whenever the user closes the GUI. The whole point of supporting both a
GUI and a shim is that they're independent surfaces over the same long-lived
state.

**System service installation as the primary launcher (launchd / systemd /
Windows service).** Rejected for now. Requires elevated permissions,
per-platform install scripts, and a more complex uninstall story. Defer to a
later spec as an additive opt-in. The current pattern is forward-compatible:
when system service support lands, the detect-or-spawn helper still works, it
just finds an already-running daemon every time.

**No discovery file — fixed port + ambient token.** Rejected. Port conflicts
on developer machines (8000 is heavily used) and shared-secret rotation would
both require either a configuration file or a discovery file. Choosing one
file with everything in it is simpler than splitting state.
