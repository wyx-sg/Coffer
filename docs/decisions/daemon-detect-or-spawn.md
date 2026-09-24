# Any Surface Finds the Daemon or Spawns It

**Status**: Accepted
**Date**: 2026-09-14
**Deciders**: Yuxing Wu
**Related**: [Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md), [Daemon Is a Resident Login Service](daemon-is-a-resident-login-service.md), [Daemon Auth and Origin Guard](daemon-auth-and-origin-guard.md), [stdio Shim Bridge](stdio-shim-bridge.md), [Session Subprocess Model](session-subprocess-model.md), spec daemon "Keep exactly one daemon per vault", spec daemon "Spawn a detached daemon from any surface that needs one", spec daemon "Publish one private discovery file", spec daemon "Decide liveness by the status call", spec daemon "Warn on a version mismatch and carry on", spec daemon "Stand down only when provably superseded", spec daemon "Own and reap the daemon's long-lived children", PR #219, PR #342

## Context

Coffer is one long-lived daemon with several clients, none of which the user
thinks of as "starting Coffer":

- `coffer-mcp-shim`, launched by Claude Code or Codex as a stdio MCP server
  every time the agent starts (see [stdio Shim Bridge](stdio-shim-bridge.md));
- the `coffer …` CLI, run ad hoc from a terminal;
- the desktop shell, which resolves a daemon with its own fixed order (spec
  desktop-app "Find or start a daemon by a fixed resolution order") but obeys
  the same rules;
- a browser tab on the UI the daemon serves.

The daemon has to outlive every one of them: one agent's shim exiting must not
take the gateway away from another agent, and a CLI command must leave the
daemon running after it returns. At the same time there must be exactly one
daemon per vault. A second daemon does not fail loudly; it splits the vault's
state between two processes and the user finds out much later.

So the question is how a daemon comes to exist, how a client finds the one that
does, and what happens when two clients arrive at once, when the one they find
is from an older install, or when one was left behind by a crash. The login
service of [Daemon Is a Resident Login Service](daemon-is-a-resident-login-service.md)
makes "no daemon" rarer but does not remove it: the service is opt-in and
macOS-only, a user can stop the daemon, and a crash leaves a gap until launchd
restarts it.

## Options Considered

### Option A — Detect-or-spawn over a discovery file, daemon as its own detached process (chosen)

The daemon is an independent process bound to `127.0.0.1`. When it binds it
writes `~/.coffer/daemon.json` (mode `0600`, atomic replace) carrying the
schema version, pid, port, a per-start token, start time and executable
(`infrastructure/daemon/pid_lock.py`, `DaemonInfo`). Every client uses the same
sequence (`surfaces/cli/_client.py`, `surfaces/shim/bootstrap.py`):

1. read `daemon.json`;
2. call `GET /api/v1/daemon/status` on the recorded port — the one
   unauthenticated route — and treat a `200` as live;
3. otherwise spawn the daemon detached (`spawn_detached_daemon` in
   `infrastructure/daemon/spawn.py`: `start_new_session=True` on POSIX,
   `CREATE_NO_WINDOW | DETACHED_PROCESS` on Windows, stdin from `/dev/null`,
   stdout and stderr appended to `~/.coffer/logs/daemon.log`) and poll until the
   file appears and the status call answers.

Pros: any client bootstraps the daemon, so the user never sees "start the
daemon first"; no privileged install; the daemon survives whichever client
started it; one file carries every per-start fact (pid, port, token) that a
client needs. Cons: ownership of the daemon is implicit, two clients can race
to spawn, a client can attach to a stale build, and a spawned daemon can be
orphaned. Each of these has a specific answer, set out under Decision. It wins
because the alternatives either put a setup step in front of every agent
session or tie the daemon's life to a process that exits.

### Option B — The user starts the daemon (`coffer daemon start`) before anything else

Pros: nothing spawns anything; ownership is explicit. Cons: every agent session
depends on a step the user has to remember, and the failure shows up inside the
agent as a broken MCP server, far from its cause. This was the CLI's behaviour
until 2026-05-30, when it printed an instruction to run `coffer daemon start`
instead of spawning; that was treated as a defect and fixed. Loses on usability.

### Option C — The entry point that needs a daemon runs the server in-process

Each client (or the first client) hosts the HTTP server itself and the daemon
dies with it. Pros: no detached process and no discovery problem for that one
client. Cons: the shim of one agent session would carry the gateway for every
other session and take it down when that agent exits; a CLI command would have
to stay resident or tear the server down on return. The point of the design is
that every entry point is an independent surface over the same long-lived
state. Loses outright.

### Option D — An OS service is the only way the daemon runs

Install a launchd agent (and equivalents elsewhere) and never spawn from a
client. Pros: one supervisor, explicit lifecycle. Cons: requires an install step
before first use, is platform-specific (only macOS has one in Coffer today), and
still leaves the gap between a crash and the restart. Coffer offers this as an
opt-in *addition* ([Daemon Is a Resident Login Service](daemon-is-a-resident-login-service.md)),
with detect-or-spawn as the path that always works.

### Option E — Socket activation (launchd / systemd listen on the port and start the daemon on first connect)

Pros: the port is always accepting; the first request starts the daemon. Cons:
platform-specific, needs the service installed first (Option D's cost), hands
the socket to a process that then spends 5–14 s booting while the first
request waits, and the per-start token still has to be published somewhere, so
a discovery file is needed anyway. Loses on portability for no saving.

### Option F — A fixed port and no discovery file

Clients assume `127.0.0.1:8000` and read the token from somewhere else. Pros:
one less file. Cons: the token is minted per start and the pid is per process,
so per-start state has to be written somewhere regardless; a user-set port
would have to be found too. One private file for all of it is simpler than
splitting it. `daemon.json` (runtime state, written out, unlinked on exit) stays
deliberately distinct from `daemon-config.json` (configuration, read in,
survives shutdown) of [Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md).

## Decision

Every surface that needs a daemon finds it through `~/.coffer/daemon.json` and
the unauthenticated status call, and spawns a detached one when none answers.
The daemon is its own process, bound to loopback, and lives until it is stopped
or superseded. Four rules make that safe:

1. **Liveness is the status call, never a bare TCP connect.** A crashed
   daemon's port can be squatted by an unrelated process; a connect would call
   that "live" and block every start. The probe timeout is 15 s
   (`_LIVENESS_PROBE_TIMEOUT` in `infrastructure/daemon/bootstrap.py`) because a
   serving daemon still warming up was measured taking about 9 s to answer, and
   at the earlier 2 s a spawn concluded nobody was live and started a second
   daemon. A stale file costs nothing at 15 s: a dead port refuses at once.
2. **One spawn lock, held until the winner is serving.** The daemon's
   probe → bind → write `daemon.json` sequence runs under an exclusive `flock`
   on `~/.coffer/daemon.lock` (`bootstrap.acquire_or_existing`), and the lock
   is released only when uvicorn reports it is serving (`entry._run_server`).
   Releasing at the write left a boot window in which a racing spawn probed the
   bound-but-not-yet-answering port, got no answer and bound again. A spawn that
   finds a live daemon under the lock returns it and binds nothing. On exit the
   daemon unlinks `daemon.json` only while it still records its own pid, so an
   orphan cannot delete the live daemon's file. Windows has no `fcntl`; there
   the liveness refusal and the atomic `os.replace` are the guards.
3. **Version skew is reported, never acted on.** Because the daemon outlives
   the CLI and shim, a freshly installed Coffer can attach to the previous
   install's daemon. `/daemon/status` reports `version` and `executable`; every
   CLI command and the shim compare it with their own build and print one
   warning line naming both versions and `coffer daemon restart`
   (`infrastructure/daemon/version_skew.py`), and the desktop shell shows the
   same as a banner. They never refuse and never kill the daemon: refusing
   would break the working half to report the confusing half, and the running
   daemon may be serving other agents.
4. **Only a daemon provably serving this vault is ever reaped.** At startup the
   daemon sweeps recorded upstream children left by a crash and sibling daemon
   processes (`orphan_sweep.startup_sweep`). A sibling is reaped only in frozen
   builds (a source run's executable is the Python interpreter, which must not
   be matched) and only when its own `HOME`, read from its environment, resolves
   to the same `~/.coffer`; a process whose environment cannot be read is left
   alone. Separately, a serving daemon re-reads `daemon.json` every 30 s and
   stands down when it names a different pid that is a live Coffer daemon
   (`bootstrap.superseded_by`, `entry._evict_when_superseded`); an absent,
   malformed or self-naming file never evicts anyone.

## Consequences

- No surface ever tells the user to start the daemon, and no agent session
  depends on a setup step.
- Every spawner goes through `spawn_detached_daemon`, so a daemon that refuses
  to start (a taken port, say) leaves its reason in `daemon.log`, which is
  where every client's timeout message points. The shim once spawned with
  `stderr` to `/dev/null` and could only say "did not come up within 10s".
- The HOME check on reaping exists because of an incident: the bundle smoke
  test starts a freshly built `coffer-daemon` under a throwaway `HOME`, and
  before the check that daemon reaped the maintainer's live one, since every
  vault runs a binary with the same name and no arguments. "Not provably ours"
  must mean "leave it alone": a wrong kill costs someone a running daemon, a
  missed one costs a port the next start names in its error.
- Self-eviction was added after ten orphaned daemons were found holding
  8000–8009 on a source install, where the frozen-only sibling reaping cannot
  run. With the fixed port of [Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md),
  a second daemon now collides and refuses instead of drifting, so eviction
  matters mainly under the test harness's port-range override.
- `infrastructure/daemon/` imports no surface (enforced by import-linter), which
  is why `entry.py` reads `daemon.json` and hands the pre-bound socket to
  uvicorn itself.
- `coffer daemon start` pre-checks the port with a real bind before spawning, so
  a squatted port gets the actionable refusal instead of a 10 s timeout. That
  check may wrongly report "free" (a `TIME_WAIT` port after a restart) but must
  never report a conflict that is not there; the lock and the liveness probe
  still decide.
- `coffer daemon stop` confirms the recorded pid is still a Coffer daemon
  (`pid_lock.pid_is_coffer_daemon`) before signalling it, and removes the stale
  file instead when it is not.
