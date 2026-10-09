## Why

The daemon already holds one spawn lock per vault, yet the user's Mac kept showing many Coffer
daemon processes. A snapshot of that Mac and a read of the code found where they come from:

- An old daemon that did not exit on a restart. Between 2026-10-04 and 2026-10-06 the new daemon's
  startup sweep had to reap one five times. A wedged daemon keeps its port, so the replacement can
  only refuse beside it, and nothing ever stops it.
- Starts that never leave. The spawn lock is waited on with no bound, so one boot that hangs makes
  every later CLI command, MCP shim, desktop launch and launchd restart queue behind it for good.
- Kills that miss. A client that gave up waiting for its spawn killed the process it started, which
  in the one-file build is only the bootloader; the real daemon kept booting unseen.
- Spawns that were not needed. The MCP shim looked for a daemon for one second, so a busy daemon got
  a spawn from every MCP session that opened meanwhile, and a start that met its own vault's busy
  daemon on the port exited 2, which the login service treats as a crash and restarts.
- Test daemons that outlive their test run, because a daemon never idles out.
- Duplicate starts left no trace: "already running" was logged below the level the daemon log keeps
  at that point, so none of the above could be counted afterwards.

Much of what looked like "many daemons" is also normal: a one-file build shows as a bootloader and a
child process, the model proxy runs the same `coffer-daemon` binary, and each agent session runs its
own shim pair. Nothing showed which processes were extra.

## What Changes

- A start waits for the spawn lock for a bounded time (two minutes) and then exits cleanly, naming
  the pid that holds it; the holder records its pid in the lock file.
- A start that finds its own vault's daemon holding the port exits 0 as a duplicate, so the login
  service does not restart it.
- The CLI no longer kills a spawn it stopped waiting for, and waits as long as `coffer daemon start`
  (30 s) before giving up.
- The MCP shim waits up to 15 s for a daemon that `daemon.json` names and that is running before it
  spawns another.
- An explicit restart forces out a daemon that will not stop: `coffer daemon restart` (SIGTERM, a
  15 s grace, then SIGKILL), the web UI's restart (the successor kills a predecessor still running
  after its 60 s wait) and the desktop shell's restart (a daemon that does not answer, or keeps its
  port after the shutdown request). Only a process proven to be a Coffer daemon of this vault is
  touched; automatic starts never kill anything.
- `coffer daemon stop` waits the same 15 s grace before reporting a daemon that did not exit, and
  points at `restart` to replace it.
- `coffer daemon status` lists any other daemon process of this vault (`other_daemon_pids` under
  `--json`), counting a one-file bootloader and its child once.
- "Already running" and the new duplicate exits are logged at WARNING so they reach the daemon log.
- Test harnesses pass `COFFER_DAEMON_EXIT_WITH_PID`; a daemon started with it shuts down once that
  pid has exited. The e2e daemon script and the shim tests set it.

## Capabilities

### Modified Capabilities

- `daemon`: bounded spawn-lock wait, duplicate exit on its own vault's port, no kill on a client
  timeout, the shim's wait for a busy daemon, forced restart, `status` listing extra daemons.
- `desktop-app`: the shell's restart forces out a daemon that will not stop.

## Impact

- Backend: `infrastructure/daemon` (bootstrap, entry, self_restart, orphan_sweep, new force_stop),
  `surfaces/cli` (`_client`, `daemon_cmd`), `surfaces/shim/bootstrap`.
- Desktop: `restart.rs`, `discovery.rs`, new `force_stop.rs`.
- Tests and harness: e2e daemon script and Playwright configs, shim tests.
- Docs: architecture "Daemon and processes" (en, zh), the daemon guide's troubleshooting notes.
- No UI change, so no design canvas change.
