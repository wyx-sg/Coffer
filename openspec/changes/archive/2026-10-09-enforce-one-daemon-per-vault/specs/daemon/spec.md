## ADDED Requirements

### Requirement: Force out a wedged daemon on an explicit restart
A restart the user asks for — `coffer daemon restart`, the web UI's restart, the desktop shell's
restart — means "replace the daemon that is there". A daemon that does not exit when asked keeps its
port, so its replacement can only refuse beside it and the wedged process stays forever. Such a
restart MUST therefore escalate: ask the daemon to stop, wait a bounded grace period, then kill its
process tree. It MUST do so only for a process it has proven to be a Coffer daemon — by its command
line, never the model proxy — that this vault's `daemon.json` names or that serves this vault, and
MUST remove the discovery file the killed daemon left behind. Automatic starts — a CLI command, the
MCP shim, the login service — MUST NOT kill a daemon.

#### Scenario: a restart replaces a daemon that does not answer
- **GIVEN** a daemon of this vault that ignores the stop signal,
- **WHEN** the user runs `coffer daemon restart`,
- **THEN** after the grace period the daemon's process tree is killed and its `daemon.json` removed,
- **AND** a new daemon is started in its place.

#### Scenario: a restart never kills a process that is not this vault's daemon
- **GIVEN** a `daemon.json` whose pid now belongs to a process that is not a Coffer daemon of this vault,
- **WHEN** a restart forces the recorded daemon out,
- **THEN** no signal is sent to that process.

## MODIFIED Requirements

### Requirement: Keep exactly one daemon per vault
There MUST be exactly one daemon per vault, and the sequence that decides it — probe for a live
daemon, bind a port, publish `daemon.json`, announce readiness — MUST run under an exclusive lock
on `~/.coffer/daemon.lock`. The lock MUST be held past the publish, until the daemon is actually
serving HTTP: released at the write, it leaves a boot window in which a racing spawn probes a
bound-but-not-yet-answering port, concludes nobody is live, and binds a second one whose publish
then orphans the first. A spawn that finds a live daemon under the lock MUST return that daemon and
bind nothing. Where the platform offers no advisory file lock, the liveness refusal and the atomic
publish MUST still hold on their own. The lock lives on the open descriptor, not on the file's
existence, so the lock file is left on disk between runs. See
[Detect-or-Spawn](../../../docs/decisions/daemon-detect-or-spawn.md).

The wait for the lock MUST be bounded (two minutes): past it the holder is a boot that is not
finishing, and a start that queues behind it forever only adds an idle process, one per CLI
command, shim, desktop launch and login-service restart. A start that gives up MUST exit cleanly
(code 0) and log which pid holds the lock; the holder MUST record its pid in the lock file for
that. A start that finds the port held by a Coffer daemon of its own vault — a daemon too busy to
answer the liveness probe — MUST likewise exit 0 as a duplicate rather than as a failure, so the
login service does not restart it. Every such duplicate exit, and the "already running" exit, MUST
reach the daemon log. A client that stops waiting for a daemon it spawned MUST NOT kill it: a boot
that is slow finishes on its own, a boot that cannot finish leaves through the bounded lock wait,
and in the one-file build the handle a client holds is only the bootloader, so a kill misses the
daemon. The MCP shim MUST wait for a daemon that `daemon.json` names and that is running as long
as the CLI's liveness probe does (15 s) before it spawns another.

#### Scenario: two racing spawns produce one daemon
- **GIVEN** no daemon is running and two surfaces (a CLI command and an MCP shim) each decide to spawn one at the same moment,
- **WHEN** both spawned processes run their detect-or-spawn sequence,
- **THEN** exactly one binds a port and publishes `~/.coffer/daemon.json`, and the other observes it is already live and exits without binding,
- **AND** the loser blocks on the spawn lock until the winner is serving HTTP, so it never probes a bound-but-not-yet-answering port and concludes nobody is there.

#### Scenario: a start stuck behind a boot that never finishes gives up
- **GIVEN** a start that holds the spawn lock and never finishes booting,
- **WHEN** another start waits for the lock for longer than the bound,
- **THEN** it exits with code 0 without binding a port or writing `daemon.json`,
- **AND** the daemon log names the pid that holds the lock.

#### Scenario: a start that meets its own vault's busy daemon leaves as a duplicate
- **GIVEN** a daemon of this vault holding the port but not answering the liveness probe in time,
- **WHEN** another start of the same vault fails to bind that port,
- **THEN** it exits with code 0, not the port-in-use code, and logs that the daemon is already running but busy.

#### Scenario: a client that stops waiting leaves its spawn alone
- **GIVEN** no daemon is running and a CLI command spawns one that does not answer within its wait,
- **WHEN** the command gives up and reports the timeout,
- **THEN** it sends no signal to the process it spawned.

#### Scenario: an MCP session waits for a busy daemon instead of spawning another
- **GIVEN** `daemon.json` names a running Coffer daemon that takes several seconds to answer,
- **WHEN** an agent starts the MCP shim,
- **THEN** the shim keeps waiting for that daemon instead of spawning a second one after a second.

### Requirement: Manage the daemon from the command line
Users MUST be able to run `coffer daemon start`, `stop`, `restart` and `status [--json]`, with the daemon down or wedged. `start` MUST key off the liveness probe rather than the
presence of `daemon.json`, MUST diagnose a port that is already held *before* spawning rather than
after a boot timeout, and MUST wait a bounded time for the spawned daemon to **answer its status call** — a published
`daemon.json` is not that, because the file is written before the daemon has finished starting and a
stale one left by a crash is there before it has started at all. A daemon that exits before it
answers (git is too old, say) MUST be reported as failed with a pointer to
`daemon.log`, never as started. That pre-flight
check MUST be allowed to report "free" when the port is not — a port in `TIME_WAIT` from the daemon
a `restart` has just stopped is bindable and must not be called a conflict — and MUST never err the
other way: a missed conflict resolves downstream as "already running", while a false one blocks a
legitimate start. `stop` MUST confirm the recorded pid is still a Coffer daemon before signalling
it, and MUST clean up the stale discovery file instead when it is not; it MUST give the daemon the
graceful-stop period (15 s) to exit and, when it does not, say so and point at `restart`. `restart`
is `stop` then `start`, and is how a setting read before the bind takes effect; a daemon that does
not exit within the period is forced out (see "Force out a wedged daemon on an explicit restart"). `status` MUST only look: with no
daemon answering — no `daemon.json`, or one whose port nothing answers on — it MUST report the
daemon as not running (`{"status": "stopped"}` under `--json`) and exit non-zero, and MUST NOT
start one. With a daemon answering, `status` MUST also report the passes in flight — the list
[resource-framework](../resource-framework/spec.md) "Report the passes in flight in one cross-kind read"
defines, each with its kind, its target and when it started — in its own section of the table form,
which says so when nothing is running, and as part of the object under `--json`. It MUST also list
every other daemon process serving the same vault — a start still booting or waiting on the lock,
or a stray — by pid (`other_daemon_pids` under `--json`), counting a one-file daemon's bootloader
and child once and never the model proxy, because one serving daemon is the rule and an extra one
is otherwise hard to tell apart from the processes a one-file build always shows. The daemon port is
read and changed with `coffer config get|set|unset daemon.port`, which MUST work with no daemon
running (see "Bind a fixed, settable port").

#### Scenario: start reports a daemon that refused to start
- **GIVEN** a stale `~/.coffer/daemon.json` and a vault the daemon refuses to open
- **WHEN** the user runs `coffer daemon start`
- **THEN** the command exits non-zero saying the daemon exited at startup and pointing at `daemon.log`, and does not print that the daemon started

#### Scenario: a recorded pid that is not ours is never signalled
- **GIVEN** a `~/.coffer/daemon.json` whose recorded pid has been recycled onto an unrelated process,
- **WHEN** the user runs `coffer daemon stop`,
- **THEN** no signal is sent to that process; the stale discovery file is removed instead, and the command says so.

#### Scenario: status reports a stopped daemon without starting one
- **GIVEN** no daemon is running,
- **WHEN** the user runs `coffer daemon status`, or `coffer daemon status --json`,
- **THEN** it reports the daemon as not running (`{"status": "stopped"}` under `--json`) and exits non-zero,
- **AND** no daemon is spawned and no `daemon.json` is written.

#### Scenario: status names the passes in flight
- **GIVEN** a running daemon with a pass over a knowledge collection and a pass over a memory partition under way,
- **WHEN** the user runs `coffer daemon status --json`, and again `coffer daemon status` once both passes have ended,
- **THEN** the JSON reports the daemon as ready and lists both passes with their kind, target and start time, oldest first,
- **AND** the later table form carries a passes section saying that no pass is running, and neither call starts a pass.

#### Scenario: status names other daemon processes of the vault
- **GIVEN** a serving daemon and a second daemon process of the same vault still starting,
- **WHEN** the user runs `coffer daemon status --json`,
- **THEN** `other_daemon_pids` lists the second process's pid and not the serving daemon's,
- **AND** the table form names it on its own line.

### Requirement: Restart itself on request
A page in a browser is served by the daemon, so it cannot stop the daemon and
start another from outside the way the desktop shell and `coffer daemon restart`
do; restarting is Coffer's own deterministic work, so the daemon MUST restart
itself on the token-gated `POST /api/v1/daemon/restart`. It MUST be a true
restart, in this order: the daemon starts a successor — the same command every
surface spawns, detached, with the daemon's own environment and the pid it
succeeds — and only then answers `202` with the port the successor binds (the
pre-bind config's, so a port saved on Settings → Daemon applies), and only
after the answer is sent takes the one graceful exit of "Shut down through one
graceful exit path". The successor MUST wait for that pid to have exited before
it takes the spawn lock or binds anything, and then starts as any daemon
starts — the same detect-or-spawn lock and liveness probe. A predecessor that
has not exited when the wait runs out is wedged, and the successor MUST force
it out (see "Force out a wedged daemon on an explicit restart") rather than
stand down beside it. A successor that cannot be started MUST answer an
error and leave the daemon serving. A second request while a restart is under
way MUST NOT start a second successor. The frozen one-file build MUST start its
successor as a new instance of itself, so the successor never relies on the
predecessor's unpacked files. A restart is recorded as a `daemon_restarted`
audit entry naming the port and the successor's pid. The successor mints a new
token, as every start does; the page reloads from the successor's origin to
receive it.

The mechanism is the same however the daemon was started — by a surface's
detached spawn, by the desktop shell or by the login service: the login
service restarts only an exit that failed, so it is not asked to restart a
deliberate one. `coffer daemon restart` keeps its own stop-then-start from
outside, because it must also work when the daemon is wedged or not running and
no route answers.

#### Scenario: a restart asked from the web ui starts a successor
- **GIVEN** a running daemon whose pre-bind config names port 8123
- **WHEN** an authenticated `POST /api/v1/daemon/restart` arrives
- **THEN** the daemon starts its successor first, answers 202 with port 8123, and only then exits gracefully
- **AND** a `daemon_restarted` audit entry records the port and the successor's pid, and a second request starts no second successor

#### Scenario: a successor that cannot start leaves the daemon serving
- **GIVEN** a running daemon whose successor cannot be started
- **WHEN** an authenticated `POST /api/v1/daemon/restart` arrives
- **THEN** it answers an error, does not exit, and records no restart

#### Scenario: the successor binds only after its predecessor has exited
- **GIVEN** a successor started by a restart, naming the pid of the daemon it succeeds
- **WHEN** it starts while that daemon is still exiting
- **THEN** it waits until that pid is gone before taking the spawn lock or binding, and after a bounded wait forces that daemon out before going on
- **AND** nothing it spawns inherits the predecessor's pid
