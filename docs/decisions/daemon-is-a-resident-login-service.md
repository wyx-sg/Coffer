# The Daemon Is Resident: It Never Idles Out, and a Login Service Restarts Only a Crash

**Status**: Accepted
**Date**: 2026-09-24
**Deciders**: Yuxing Wu
**Related**: [Detect-or-Spawn](daemon-detect-or-spawn.md), [Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md), [SeaTalk WebSocket Inbound](seatalk-websocket-inbound.md), spec daemon "Run as a login service", spec daemon "Change residency from the settings page or the command line", spec daemon "Stand down only when provably superseded", spec desktop-app "Restart by stopping the running daemon first", PR #412, PR #431

## Context

Most of what talks to Coffer has no window: an agent in a terminal, an editor
plugin, a chat channel whose messages arrive at any hour. A daemon that exists
only because something started it is down at exactly those moments, and whoever
asks first pays the cold start — measured at 4.8–13.9 s on a real vault
(PR #412: unpacking the frozen binary, migrations, MCP upstreams and channel
listeners all come up before uvicorn accepts). A channel is worse off than an
agent: no client is there to spawn the daemon when a message arrives, so a down
daemon is a message nobody answers.

Two questions follow. When does the daemon start without being asked? And when,
if ever, does it stop without being asked?

## Options Considered

### Option A — Never idle out; an opt-in login service that restarts only an unsuccessful exit (chosen)

The daemon serves until it is stopped (`coffer daemon stop`, the desktop shell's
restart, system shutdown) or superseded by another daemon (spec daemon "Stand
down only when provably superseded"). It has no idle timer.

On macOS, `coffer daemon service install` — or the Start at login switch in
Settings, which calls `PUT /api/v1/daemon/residency` — writes a per-user
launchd agent `dev.coffer.daemon` (`infrastructure/daemon/login_service.py`)
with:

- `RunAtLoad: true`, so the daemon is up when the user logs in;
- `KeepAlive: {SuccessfulExit: false}`, so a crash is restarted and a clean
  exit is not;
- `EnvironmentVariables.PATH` taken from the user's login shell, because a
  launchd agent otherwise gets a minimal `PATH` and the `npx` / `uvx` MCP
  upstreams the daemon spawns resolve to nothing;
- `ProgramArguments` pointing at the public `~/.coffer/bin/coffer-daemon`
  symlink, not the versioned directory behind it, because deploys prune old
  version directories and a launchd job whose program is gone fails silently;
- stdout and stderr into the same `daemon.log` every other surface reads.

Pros: the daemon is there before anything asks; a crash recovers without a
client having to notice; a deliberate stop stays stopped; there is no clock for
a subsystem to forget to hold. Cons: a daemon nobody uses stays resident — one
process plus whatever upstreams its sessions started. Accepted: `coffer daemon
stop` or removing the service ends it.

### Option B — Stand down after an idle window, with holds for subsystems that must stay reachable

The design this replaced (PR #412, removed in PR #431). The daemon exited after
twelve hours without a request (configurable, or never); an ASGI middleware fed
a monotonic clock on every request, and subsystems that had to be reachable — a
channel's inbound listener above all, an MCP stream an agent keeps open
overnight — registered named holds to keep it open. Pros: a login service does
not mean a Python process, its upstreams and channel listeners surviving every
weekend nobody worked. Cons: the login service already decides when the daemon
starts, so the window only added a way for it to be down when a message
arrived; every subsystem that must be reachable had to remember to hold the
clock, and one that forgot was a bug by construction; it cost a setting, a CLI
group (`coffer daemon idle`), a REST field and a UI control. Loses: the owner
decided the daemon never stands down on its own.

### Option C — Keep the idle machinery, default the window to "never"

"Never" was already a value of the setting, so this was the smallest change.
Pros: nothing deleted, users who want an idle exit keep it. Cons: keeps the
clock, the hold registry, the per-request middleware, the CLI group and the UI
control whose only remaining use is to switch on behaviour the project has
ruled out — and keeps the "forgot to hold" bug class alive for anyone who does.
Loses to deleting it (see the archived change
`openspec/changes/archive/2026-09-24-remove-daemon-idle-stand-down/design.md`).

### Option D — Login service with `KeepAlive: true`

Pros: simplest supervisor configuration; the daemon is always up. Cons: the
daemon exits cleanly on purpose — `coffer daemon stop`, the desktop shell's
restart (which stops the running daemon before starting the next), and standing
down when superseded — and an unconditional `KeepAlive` restarts it a second
later each time, fighting the user's own stop and the daemon that superseded
it. Nothing is gained, because every client can start a daemon. Loses.

### Option E — Spawn on demand only, no login service

Pros: no OS integration, nothing to install or uninstall. Cons: the cold start
lands on whoever asks first, once per gap, and a channel has nobody to ask.
Detect-or-spawn remains the path that always works
([Detect-or-Spawn](daemon-detect-or-spawn.md)), but on its own it leaves the
daemon down at the moments it is wanted. Loses as the only mechanism.

## Decision

The daemon never exits for want of use. Residency is the login service alone:
an opt-in, reversible, per-user launchd agent that starts the daemon at login and
restarts it only after an unsuccessful exit. Installing and removing it works
from the CLI with no daemon running and from the settings page; removing it
does not stop a running daemon.

Rules a future change must respect:

- The service must restart only an unsuccessful exit. Every deliberate stop
  must be a clean exit (exit code 0) so the service lets it stand.
- Nothing in `login_service.py` boots a loaded job out. Once launchd has
  started the daemon, the running daemon *is* the job, and the install and
  uninstall are usually reached from the Settings page that daemon serves;
  `launchctl bootout` would kill the process answering the request. Writing or
  deleting the plist is enough for "does it start at login"; a loaded job stays
  loaded until logout.
- No subsystem may assume the daemon goes away on its own. A channel listener,
  an SSE stream or a scheduled worker runs for as long as the daemon does.

## Consequences

- A channel message or an agent's first `coffer__*` call of the day finds a
  daemon already serving, without a cold start, once the service is installed.
- The daemon's own lifetime and the lifetime of an MCP session are separate
  things: idle MCP sessions are still reaped by the `/mcp` session reaper
  ([Session Subprocess Model](session-subprocess-model.md)), which is not an
  idle exit of the daemon.
- `daemon-config.json` no longer has an idle setting. An `idle_shutdown_hours`
  key an earlier build wrote is ignored on read and dropped by the next write
  (`_RETIRED_KEYS` in `infrastructure/daemon/config.py`); no migration is
  involved because the file is read before the database opens. A downgrade
  reads the absent key as that build's own default.
- `GET`/`PUT /api/v1/daemon/residency` carry only `login_service_supported` and
  `login_service_installed`.
- The login service is macOS-only (`login_service.is_supported`). Elsewhere the
  daemon is resident once started but nothing starts it at login.
- The daemon raises its own file-descriptor soft limit at start
  (`entry._raise_fd_soft_limit`), because launchd hands it about 256, which a
  long-lived process with many upstreams can reach.
