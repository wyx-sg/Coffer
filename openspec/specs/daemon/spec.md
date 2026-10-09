# Daemon

## Purpose

The daemon is the Coffer process itself: how exactly one daemon comes to exist per vault, how
every other surface finds it, what guards its loopback HTTP surface, how it serves the web UI,
the OS actions it performs on the user's behalf, the log it writes, and how it is distributed as
a terminal install. What the daemon serves *through* that surface belongs to the specs that own
each kind. Every other surface in the product — the CLI, the MCP shim, the web UI, the desktop
shell — is a client of this one, so a user never sees "start the daemon first" and never ends up
with two: a second daemon does not fail loudly, it splits the vault's state between two processes
and the user finds out much later. The UI it serves lives at an address that does not move, so a
bookmark keeps working, stays authenticated and keeps what the browser stored against that origin,
while a page on somebody else's site can read none of it. It lets a browser tab reach the machine
where a page cannot by itself — a real folder chooser, opening a managed file in the user's editor,
revealing it in the file manager — and it ships as one archive that needs no runtime and no source
checkout.

The single user runs Coffer on their own machine: loopback binding plus a locally minted token is
the whole of the access model, there is no multi-tenant or remote-access requirement, and
nothing Coffer runs is reachable from off the machine. Process inspection is available for processes the user owns; wherever it is
not, every rule here reads the answer as "not ours" and does nothing, which is the safe direction
for all of them. The desktop shell of the desktop-app spec reads `daemon.json` and drives
`POST /daemon/shutdown` from Rust, in a separate crate: the file's shape is this spec's to change,
and a change to it is a change to that shell. There is no fleet, no leader election and no
daemon-to-daemon protocol; the daemon spawns children but does not install runtimes or package
managers for them, and the `.dmg` and the shell inside it belong to the desktop-app spec, which
wraps the same four binaries this spec builds.

The CLI carries only what needs it (see [resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"), so most daemon operations are REST and web UI only, and three differences are deliberate. The pre-bind port setting is reachable from the CLI as well as from Settings, because it must work with no daemon
running. The `/api/v1/fs/*` routes are REST-only because their only caller is a web page that
cannot reach the OS by itself, while a terminal user already has `cd`, `$EDITOR` and their
platform's own open command. `POST /daemon/shutdown` has no dedicated CLI verb because
`coffer daemon stop` reaches the same exit through a signal. `COFFER_PORT_RANGE_START` /
`COFFER_PORT_RANGE_END` are test-harness machinery, not product behaviour: they are the one
surviving path on which a start scans for a free port, they deliberately outrank the user's
setting so a test run is hermetic on a machine whose vault has a port pinned, and no user-facing
surface sets them.

## Requirements

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

### Requirement: Spawn a detached daemon from any surface that needs one
Any surface that needs a daemon and finds none MUST spawn one itself, detached, rather than
telling the user to start one — the CLI, the MCP shim and the desktop shell of the desktop-app spec
alike. The spawned process MUST outlive the caller, MUST take no stdin, and MUST send its output to
the daemon log (see "Write one bounded daemon log in one format"), so that a daemon which refuses
to start explains itself in the file the caller's error message names. Resolution MUST work from
source (the daemon module under the running interpreter) and frozen (the `coffer-daemon` sibling of
the running binary, then one on `PATH`, then the one staged inside an installed macOS app bundle).

#### Scenario: a surface that finds no daemon starts one detached
- **GIVEN** no daemon is running and a surface needs one,
- **WHEN** it spawns the daemon,
- **THEN** the daemon process runs in a session of its own, so it outlives the caller, and reads end-of-file on its stdin,
- **AND** everything it writes to stdout and stderr — including a refusal to start — is appended to `daemon.log` in the configured log directory.

### Requirement: Publish one private discovery file
`~/.coffer/daemon.json` MUST be the single discovery file: schema version, pid, port, token, start
time and the daemon's executable, written atomically at mode `0600` so a racing publish can never
be read half-written and the token is never readable by another user. It is runtime state that
comes *out* of the daemon, deliberately distinct from the configuration that goes *in* (see "Bind a
fixed, settable port"): it MUST be unlinked at exit, and only while it still records this process's
own pid, so an orphaned daemon cannot delete the live daemon's file on its way out. An absent or
malformed file MUST read as "no daemon", never as an error.

#### Scenario: a published discovery file is private and complete
- **GIVEN** a daemon starting against a vault with no discovery file,
- **WHEN** it binds its port and publishes `~/.coffer/daemon.json`,
- **THEN** the file is at mode `0600` and records the schema version, pid, port, token, start time and executable, and the port it records is the one the daemon holds,
- **AND** when the file is later malformed, a client reading it sees "no daemon" rather than an error.

### Requirement: Answer the status probe without a token
`GET /api/v1/daemon/status` MUST be unauthenticated and MUST answer as soon as the daemon is
serving, because it is the readiness probe every other rule here keys off. The port only opens once
the daemon has finished wiring itself up — the server accepts connections after its startup hook
returns — so no request can be answered before then, and a client that has just spawned the daemon
MUST wait a bounded time for the probe to answer rather than read a refused connection as a
failure. It MUST report the lifecycle phase (`ready`; `draining` once shutdown has begun — the
daemon keeps answering for a short moment after shutdown begins, before it stops listening, so the
phase can be observed, and it MUST NOT leave its port listening with nobody accepting once it has;
or `setup` while it waits for git, with what it waits for, as "Wait in a setup state when git is
missing or too old" describes), the
bound port, the start time, the build's version and the executable answering. It MUST also report
the on/off state of every registered experimental feature as a `features` map — one
entry each for `knowledge` and `memory` (spec
[experimental-features](../experimental-features/spec.md) "Decide a feature's state per machine") —
and this machine's id and name, the identity a channel is bound to, which is on the status because
it belongs to the machine rather than to sync. It MAY carry a count of registered,
enabled, healthy and unhealthy upstreams when those are available, and MUST still answer when they
are not.

#### Scenario: daemon status reflects ready state
- **GIVEN** the daemon has just been started,
- **WHEN** `GET /api/v1/daemon/status` is called,
- **THEN** the response reports `status: "ready"`, a non-zero `port`, a `started_at` timestamp, the daemon's `version` and its `executable` — and the same port and start time are written to `~/.coffer/daemon.json`,
- **AND** the call succeeds with no token, because it is the readiness probe every other lifecycle rule keys off,
- **AND** a CLI or shim whose own version differs from the reported one prints a one-line warning naming both builds and the executable, and carries on.

#### Scenario: a daemon that is shutting down reports draining
- **GIVEN** a running daemon that has been asked to stop
- **WHEN** `GET /api/v1/daemon/status` is called after shutdown has begun and before the daemon stops listening
- **THEN** the response reports `status: "draining"`
- **AND** once the daemon has stopped listening, a connection to its port is refused rather than left waiting

#### Scenario: daemon status names this machine and its features
- **GIVEN** a running daemon
- **WHEN** `GET /api/v1/daemon/status` is called with no token
- **THEN** the response carries a `features` map with one entry per registered experimental feature (`knowledge` and `memory`), and this machine's `machine_id` and `machine_name`

### Requirement: Decide liveness by the status call
Liveness MUST be decided by that status call against the recorded port — never by a bare TCP
connect, which after a crash false-positives on an unrelated process that has since squatted the
port and would then block every start. A squatter is therefore never mistaken for a daemon; the
start refuses and names what holds the port. The probe timeout MUST outlast the slowest status a
warming daemon can produce, because a timeout is indistinguishable from "nobody is live" and
produces exactly the second daemon "Keep exactly one daemon per vault" exists to prevent. A `200`
whose body is not a JSON object still counts as live: a liveness decision MUST NOT hinge on the
payload.

#### Scenario: a stale discovery file does not stop a start
- **GIVEN** a `~/.coffer/daemon.json` left behind by a daemon that was killed without cleaning up, naming a port nothing is listening on,
- **WHEN** any surface needs a daemon,
- **THEN** the liveness probe fails, a fresh daemon is spawned, and the stale file is replaced — rather than the surface reporting "daemon already running" and then failing to connect.

### Requirement: Warn on a version mismatch and carry on
A caller that attaches to a daemon built from a different version MUST warn, naming both versions,
the daemon's executable, and the command that replaces it — and MUST carry on. This is detection,
not refusal: the daemon outlives the CLI and shim processes that attach to it, so a freshly
installed Coffer silently reuses the previous install's daemon, and refusing would break the
working half in order to report the confusing half. A daemon that reports no version, or a body
that will not parse, MUST read as "cannot tell", never as a mismatch.

#### Scenario: a daemon that cannot state its version is never called a mismatch
- **GIVEN** a live daemon the CLI attaches to,
- **WHEN** its status reports a version other than the CLI's own,
- **THEN** the CLI prints one warning line naming both versions, the daemon's executable and `coffer daemon restart`, and still hands back a working client,
- **AND** when the status reports no version, a non-string version, or no parseable body, nothing is printed.

### Requirement: Stand down only when provably superseded
A serving daemon MUST periodically re-read `daemon.json` and stand down when it names a *different*
pid that is a *live Coffer daemon* — the only positive evidence that it has been superseded. An
absent, malformed or self-naming file, or a recorded pid that is dead, recycled, or not a Coffer
daemon, MUST leave it serving: deleting the discovery file must not take the one healthy daemon
down with it. A process that cannot be inspected reads as "not a daemon". A check that fails MUST
be logged and retried, never acted on.

#### Scenario: a superseded daemon stands down
- **GIVEN** a serving daemon whose `~/.coffer/daemon.json` now records a different pid, and that pid is a live Coffer daemon,
- **WHEN** the daemon's periodic supersession check runs,
- **THEN** it shuts itself down and frees its port,
- **AND** the same check leaves the daemon serving when the file is absent, malformed, records its own pid, or records a pid that is dead or belongs to something that is not a Coffer daemon.

### Requirement: Shut down through one graceful exit path
Shutdown MUST be graceful and MUST have one exit path. `SIGTERM` and `SIGINT` run it; the
token-gated `POST /api/v1/daemon/shutdown` answers `204` and then signals this same process rather
than tearing down inline, so an API stop and a signal stop cannot diverge. Exit MUST release
`daemon.json` per "Publish one private discovery file" and terminate the long-lived children of
"Own and reap the daemon's long-lived children".

#### Scenario: stopping the daemon leaves no discovery file
- **GIVEN** a running daemon,
- **WHEN** it is stopped — by `coffer daemon stop`, by `SIGTERM`, or by an authenticated `POST /api/v1/daemon/shutdown`,
- **THEN** the process exits through the same signal path in every case, `~/.coffer/daemon.json` is unlinked, and the long-lived children it spawned are terminated,
- **AND** an unauthenticated shutdown request is rejected without stopping anything.

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

### Requirement: Own and reap the daemon's long-lived children
The daemon MUST spawn, record and terminate every long-lived child it owns — such as an agent
app-server — through one path: recording the child's pid is
inseparable from spawning it, and termination is one `SIGTERM` → bounded wait → `SIGKILL` → bounded
wait ladder whose pid record is dropped only because the child was reaped here. Each child's record
is one file naming its pid and command line. At startup the daemon MUST sweep what a previous crash
left behind: recorded children, and sibling daemon processes **provably serving this same vault**.
"Not provably ours" MUST mean "leave it alone" — a candidate whose vault cannot be read, or a
matching executable running against another `HOME`, MUST NOT be touched, because a wrong kill costs
somebody a running daemon while a missed one costs only a port the next start reports.

#### Scenario: the daemon reaps only the children it can prove are its own
- **GIVEN** a previous daemon crashed leaving a recorded long-lived child running, and another daemon binary is running against a different vault under a throwaway `HOME`,
- **WHEN** a daemon starts and runs its startup sweep,
- **THEN** the recorded orphan is terminated, and the daemon serving the other vault is left untouched — anything not provably serving this vault is left alone.

### Requirement: Bind a fixed, settable port
The daemon's listening port MUST be **fixed by default and settable**, so a browser bookmark to
Coffer's UI keeps working across restarts. With nothing configured the daemon MUST bind exactly
`38470` and MUST NOT scan for an alternative; a drifting origin is not merely a broken bookmark,
because browser `localStorage` is keyed by origin, so the UI language, sidebar state and
preferred editor silently reset when the port moves and nothing connects the two events for the
user.

The setting MUST live in a file the daemon reads **before** it binds — `~/.coffer/daemon-config.json`,
mode `0600`, merged rather than replaced and surviving shutdown — because the port is chosen before
the database is opened and before migrations run, so no database-backed setting can carry it. It
MUST NOT be an environment variable: the daemon is spawned detached by whichever surface first
needs one, inheriting that caller's environment, which a shell profile does not reach and a
GUI-launched agent never had.

When a port is configured the daemon MUST bind exactly that port and MUST NOT fall back to another
— silently moving is the behaviour the setting exists to stop. When it cannot be bound the daemon
MUST refuse to start and MUST report which process holds the port and the exact commands that
resolve it. A config file that will not parse MUST warn and fall back to the default rather than
stopping the boot, since an unbootable daemon cannot be repaired from the UI it serves.

Users MUST be able to read and change the setting **from the CLI** as the key `daemon.port` of the
generic `coffer config` command ([resource-framework](../resource-framework/spec.md): one key
registry, typed validation, `unset` returns a key to its default) — `coffer config get daemon.port`
prints the configured port or the 38470 default, `coffer config set daemon.port <n>` pins one, and
`coffer config unset daemon.port` returns to 38470. Those three MUST read and write the pre-bind file
directly and MUST work with no daemon running, because a daemon that cannot bind its port is exactly
the state the setting has to be fixable from — the CLI stays the escape hatch where a squatted port
is diagnosed. The running daemon MUST also accept a new port from the web UI's Settings → Daemon,
through `PUT /api/v1/daemon/port`: the value MUST be a whole number from 1024 to 65535 and a port no
other process holds — the port the daemon itself answers on counts as free — and is otherwise
refused with the reason, naming the holder of a taken port. The route MUST write the pre-bind file
exactly as `coffer config set daemon.port` does and answer that the change is pending: the daemon
keeps answering on its current port. A change takes effect at the next start, which
`coffer daemon restart` — or Restart now on Settings → Daemon, which is the desktop shell's restart
in the shell and the daemon's own ("Restart itself on request") in a browser — applies in one step. After a restart on a
new port the daemon records it in `~/.coffer/daemon.json`, so the desktop shell, the CLI and the MCP
shim find it by the discovery file as they find any daemon, and no agent's configuration needs a
rewrite: Coffer's MCP entry in an agent's config runs
the shim, and the memory delivery hook runs `coffer memory hook` (an internal entry point, hidden from help), and both find the daemon through
`daemon.json` when they run rather than naming a port, so every agent reconnects without a manual
step. This setting is deliberately outside the audit obligation every kind inherits: it is
neither a resource nor a capability but process configuration read before the database opens, and
the CLI that owns it must work with no daemon running — so the audit table is unreachable on
exactly the path that matters most, and recording a change only when a daemon happens to be up
would be less honest than recording none.

#### Scenario: the daemon binds the same port every start
- **GIVEN** no port has been configured, so the daemon's default of 38470 applies,
- **WHEN** the daemon is stopped and started again — by the user, by the CLI, or auto-spawned by an MCP shim, which inherits no shell profile,
- **THEN** it binds 38470 every time and records it in `~/.coffer/daemon.json`, so a browser bookmark to Coffer's UI keeps working and nothing the browser stored against that origin is lost.

#### Scenario: a configured daemon port survives restarts
- **GIVEN** the user has moved the daemon's port with `coffer config set daemon.port <n>`,
- **WHEN** the daemon is stopped and started again by any of those routes,
- **THEN** it binds that same port every time and records it in `~/.coffer/daemon.json`.

#### Scenario: a port that is taken refuses to start and says what holds it
- **GIVEN** the port the daemon would bind — its 38470 default, or one the user configured — is already held by another process,
- **WHEN** the daemon starts,
- **THEN** it refuses to start rather than binding a different port, and the message names the process holding the port and the commands that resolve it — free that process, or `coffer config set daemon.port <other>`.

#### Scenario: the port key is read and changed with no daemon running
- **GIVEN** no daemon is running and no port has been configured,
- **WHEN** the user runs `coffer config get daemon.port`, then `coffer config set daemon.port 8123`, then `coffer config get daemon.port`, then `coffer config unset daemon.port`,
- **THEN** the first prints the 38470 default, the set writes 8123 into `~/.coffer/daemon-config.json`, the second get prints 8123, and the unset leaves the file carrying no port so the default applies again,
- **AND** no daemon is spawned, no database is opened and no audit entry is recorded.

#### Scenario: a port set from the settings page is pending until restart
- **GIVEN** a running daemon on port 38470
- **WHEN** `PUT /api/v1/daemon/port` is sent with 8123, and then with a port another process holds
- **THEN** the first answers that 8123 is pending, `~/.coffer/daemon-config.json` carries 8123 and the daemon still answers on 38470
- **AND** the second is refused naming the process that holds the port, and the file is unchanged

#### Scenario: after a restart on a new port every agent reconnects
- **GIVEN** a daemon configured for 8123 while answering on 38470, and Claude Code and Codex connected to Coffer
- **WHEN** the daemon is restarted
- **THEN** it binds 8123 and records it in `~/.coffer/daemon.json`, each agent's Coffer MCP entry and delivery hook name no port and are left as they are, and the discovery the CLI, an MCP shim and the hook share finds the daemon on 8123

### Requirement: Run as a login service
The daemon MUST be installable as a **login service** — on macOS, a per-user launchd agent — so
that it is running before anything asks for it, and is restarted when it dies badly. Started only on
demand, the daemon is down at exactly the moments it is wanted: an agent's first `coffer__*` call of
the day, a channel message arriving while no window is open, a terminal session in a directory
nobody has opened Coffer from. Each of those clients can start one, and each then pays the seconds a
cold start takes, once per gap.

The service MUST restart the daemon **only on an unsuccessful exit**. A deliberate exit — `coffer
daemon stop`, the shutdown the desktop shell's restart asks for (see
[desktop-app](../desktop-app/spec.md) "Restart by stopping the running daemon first"), or standing down because another daemon superseded it
(see "Stand down only when provably superseded") — is a clean exit, and a supervisor that restarted
those too would fight the user's own stop and the daemon that superseded it; nothing is lost by
letting one stand, because every client can start a daemon.

It MUST carry the user's own `PATH`, read from their login shell: a login service otherwise
inherits a minimal one, and the `npx` / `uvx` MCP upstreams the daemon spawns then resolve to
nothing — and the environment the install itself runs in is no better a source, since it is usually
the daemon's, which was commonly spawned by a GUI-launched editor and has exactly that minimal
`PATH`. It MUST start the build that is current rather than the one that was current when it was
installed: deployed binaries live under a per-version directory whose older entries are pruned (see
"Deploy frozen sibling binaries and back up the history database before migrating"), so a service pinned to a
versioned path stops working two upgrades later, and a supervisor that cannot execute its program
fails silently — which is the one way autostart could stop without anyone finding out. It MUST
write to the daemon log (see "Write one bounded daemon log in one format") rather than a file of
its own. Installing and removing it MUST be done from Settings → Daemon (see "Change residency from the settings page or the command line"), and MUST
be reversible without trace: removing it MUST NOT stop a daemon that is already running, and MUST
unload it from launchd — at once when no process runs under it, otherwise as that daemon exits, so a
crash after the user switched the service off is never restarted. See
[Detect-or-Spawn](../../../docs/decisions/daemon-detect-or-spawn.md).

#### Scenario: the daemon is up before anything asks for it
- **GIVEN** a machine where the login service is installed and no Coffer window is open,
- **WHEN** the user logs in,
- **THEN** the daemon is started by the system, with the user's own `PATH`, logging to the daemon log,
- **AND** a daemon that dies badly is restarted, while one that exited cleanly on purpose is left alone.

#### Scenario: removing the login service unloads it without stopping the daemon
- **GIVEN** an installed login service whose launchd job is the running daemon
- **WHEN** the service is removed
- **THEN** the daemon keeps running and answers the request that removed it
- **AND** when that daemon exits, its launchd job is booted out, and a service whose job has no running process is booted out at once

### Requirement: Bind every endpoint to loopback only
The daemon MUST bind every HTTP endpoint it exposes — the management API and the MCP protocol
endpoint alike — to the loopback interface only.

#### Scenario: the daemon listens on loopback only
- **GIVEN** a daemon starting against an empty vault,
- **WHEN** it binds its listening socket and hands it to the HTTP server that serves both the management API and `/mcp`,
- **THEN** the socket is bound to `127.0.0.1`,
- **AND** the server is given only that already-bound socket and no host of its own, so nothing can widen it off loopback.

### Requirement: Require a token on every management call
The daemon MUST require an authentication token on every management API call. The token is minted
locally at startup, published only in the user-only-readable `daemon.json` (see "Publish one
private discovery file"), and rotatable. `GET /api/v1/daemon/status` is the one deliberate
exemption (see "Answer the status probe without a token"). The API's schema,
`GET /api/v1/openapi.json`, MUST need the token like any other management call, and the
daemon MUST NOT serve the framework's interactive API pages (`/docs`, `/redoc`) at all.

#### Scenario: a management call without the token is refused
- **GIVEN** a daemon with an active token,
- **WHEN** any route under `/api/v1` other than `/api/v1/daemon/status` is called with no token, or with a token that is not the active one,
- **THEN** it is refused with `401` before the route does anything,
- **AND** `/api/v1/daemon/status` still answers with no token.

#### Scenario: the API schema is served only to a token holder
- **GIVEN** a daemon with an active token,
- **WHEN** `/api/v1/openapi.json` is read with no token, with a wrong one and with the active one, and `/openapi.json`, `/docs` and `/redoc` are requested,
- **THEN** the schema is refused with `401` until the active token is sent, and then answers with the management routes,
- **AND** nothing answers at `/openapi.json`, `/docs` or `/redoc`.

### Requirement: Rotate the token over REST and on the command line
Rotation MUST be reachable through `POST /api/v1/daemon/rotate-token`, which `coffer daemon rotate-token` calls. It MUST mint a fresh token, rewrite `daemon.json` atomically at mode
`0600` — never leaving the file at wider permissions for any window — publish the new value to the
in-process check so the accepted token and the token "Hand the browser its token in the served
page" injects cannot drift apart, and record a `token_rotated` audit entry. That audit obligation
stands on its own here rather than inheriting the framework's per-resource rule: a token is neither
a resource nor a capability, and a secret changing hands is exactly the event a local-only posture
is worth recording.

#### Scenario: rotating the daemon token invalidates the previous one
- **GIVEN** the daemon has issued an auth token,
- **WHEN** the user invokes the rotate-token operation, through `POST /api/v1/daemon/rotate-token`,
- **THEN** subsequent management API calls with the previous token are rejected with 401, calls with the new token succeed, the new value reaches `~/.coffer/daemon.json` without the file ever existing at wider than user-only permissions, and the rotation is recorded as a `token_rotated` audit entry.

### Requirement: Refuse a request whose Host or Origin is not the daemon's own
The daemon MUST check two headers on every request it answers before any route sees the request. This covers the management API, the `/mcp` endpoint, the `/api/v1/events` stream, any websocket, the status probe and the served web UI. It applies to every listener the daemon opens.

- **Host.** The daemon MUST refuse a request whose `Host` header does not name `127.0.0.1`, `localhost` or `[::1]` together with the port the request arrived on. It answers `403` with error code `HOST_NOT_ALLOWED`. A missing `Host` is refused. A `Host` with no port means port 80. Binding to loopback (see "Bind every endpoint to loopback only") stops a remote host. It does not stop a **browser** on a page whose hostname an attacker re-resolves to `127.0.0.1`. That is DNS rebinding: the browser treats the page as same-origin, so CORS does not apply. Rebinding does not change the `Host` header, so the request still names the attacker's hostname and is refused before it can read a token out of the served document. This check is what makes "Hand the browser its token in the served page" safe.
- **Origin.** The daemon MUST refuse a request that carries an `Origin` header unless that origin is one of Coffer's own, answering `403` with error code `ORIGIN_NOT_ALLOWED`. Coffer's own origins are:
  - the daemon's web origins on the port the request arrived on: `http://127.0.0.1:<port>`, `http://localhost:<port>` and `http://[::1]:<port>`;
  - the desktop app's origins, `tauri://localhost` and `http://tauri.localhost`;
  - the Vite dev origins `http://localhost:5173` and `http://127.0.0.1:5173`, only when `COFFER_DEV_CORS=1` is set;
  - when `COFFER_CORS_ORIGINS` is set, exactly the origins it lists, in place of the desktop and dev entries.
- **No Origin.** A request with no `Origin` header MUST go on to the ordinary token check. This is how the CLI, the shim, agents' MCP clients and `curl` send requests.
- **CORS.** CORS MUST grant only these origins. It never grants a wildcard and never allows credentials.
- **Logging.** Each distinct refused value is logged once.

See [Daemon Auth and Origin Guard](../../../docs/decisions/daemon-auth-and-origin-guard.md).

#### Scenario: a rebound page is refused before it can read the token
- **GIVEN** a page on an attacker-controlled origin whose hostname resolves to `127.0.0.1`, which the browser therefore treats as same-origin with the daemon,
- **WHEN** it fetches any daemon URL, including `/`, so that the request carries `Host: evil.example:<port>`,
- **THEN** the daemon refuses the request with `403 HOST_NOT_ALLOWED` and the body carries no token,
- **AND** a request that names a loopback address on another port is refused the same way, while the same request addressed to `127.0.0.1:<port>`, `localhost:<port>` or `[::1]:<port>` is served normally.

#### Scenario: a request from a page on another site is refused on every surface
- **GIVEN** a running daemon with no development opt-in,
- **WHEN** a request carrying `Origin: https://evil.example`, the Vite origin, a loopback origin on another port, or `Origin: null` reaches a management route, `/mcp`, `/api/v1/events`, the status probe, the served page, or a CORS preflight, even with the right `Host` and a valid token,
- **THEN** the daemon answers `403 ORIGIN_NOT_ALLOWED` without running the route, and grants no `Access-Control-Allow-Origin`.

#### Scenario: Coffer's own pages and clients that send no Origin are let through
- **GIVEN** a running daemon on `<port>`,
- **WHEN** a request arrives with no `Origin`, or with `Origin` set to `http://127.0.0.1:<port>`, `http://localhost:<port>`, `http://[::1]:<port>`, `tauri://localhost` or `http://tauri.localhost`,
- **THEN** the guard lets it through: the status probe answers, and a management route, `/mcp` and `/api/v1/events` answer with their own token check,
- **AND** the desktop app's preflight is granted its origin.

#### Scenario: a development origin is let through only when opted in
- **GIVEN** a daemon started without `COFFER_DEV_CORS` or `COFFER_CORS_ORIGINS`,
- **WHEN** a request carries `Origin: http://localhost:5173`,
- **THEN** it is refused with `403 ORIGIN_NOT_ALLOWED`,
- **AND** with `COFFER_DEV_CORS=1` the same request is let through while a foreign origin is still refused,
- **AND** with `COFFER_CORS_ORIGINS=http://localhost:5174` only the listed origin and the daemon's own origins are let through.

### Requirement: Serve the built web UI from the daemon's own origin
The daemon MUST serve the built web UI itself, as static files, at its own loopback origin, so the
UI is same-origin with the management API. Cross-origin access MUST therefore be off by default for
every web origin; the desktop shell's own origins (`tauri://localhost`, `http://tauri.localhost`) are
the one standing exception, since the shell loads the same UI from them and the bearer token, not the
origin, is the boundary ([desktop-app](../desktop-app/spec.md)). The Vite dev-server origins stay reachable only behind the existing `COFFER_DEV_CORS` opt-in. An
install with no built UI — the normal state of a source checkout before `npm run build` — MUST skip
the mount and keep serving the API. See
[Daemon Auth and Origin Guard](../../../docs/decisions/daemon-auth-and-origin-guard.md).

#### Scenario: the built UI is served same-origin and a missing build leaves the API up
- **GIVEN** a daemon with a built web UI and no `COFFER_DEV_CORS` opt-in,
- **WHEN** the browser loads `/` and one of its assets from the daemon's origin, and a page on another web origin — including the Vite dev server's — preflights a management call,
- **THEN** the UI and its asset are served from the daemon's origin, and the preflight is granted no `Access-Control-Allow-Origin`,
- **AND** with `COFFER_DEV_CORS=1` the Vite origin is granted, and a daemon with no built UI still answers the API while `/` is a plain `404`.

### Requirement: Hand the browser its token in the served page
The daemon MUST hand the browser its API token in the `index.html` it serves, as a
`window.__COFFER_TOKEN__` global injected into the document head, sourced from the same in-process
token the header check of "Require a token on every management call" compares against so the two
cannot drift. It MUST do so for **every** route that resolves to that document — the bare `/` and
every client-side route alike — and MUST serve it `Cache-Control: no-store` with no ETag or
Last-Modified, because the document now carries a per-daemon secret and a cached copy would hand a
restarted daemon's browser the previous daemon's dead token. The page MUST NOT persist the token: a
stored token outlives the daemon that minted it, and the daemon mints a new one on every start. The
API token MUST NOT appear in a URL at any point — a URL lands in browser history, which would
contradict the loopback-plus-token posture of "Bind every endpoint to loopback only" and "Require a
token on every management call"; the response body is subject to none of that. The desktop shell, which opens the UI, MUST
therefore carry no secret of its own: it reads the daemon's real port from `daemon.json` and
opens its window at that origin.

#### Scenario: a page served by the daemon is authenticated by the daemon
- **GIVEN** a daemon that has restarted since the browser last loaded the UI, and therefore minted a new token,
- **WHEN** the browser opens any page the daemon serves — the bare `/`, a client-side route such as `/agents`, a bookmark, or a plain reload — whether it got there through the desktop shell or by typing the address,
- **THEN** the served `index.html` carries that daemon's live token as `window.__COFFER_TOKEN__`, the UI renders authenticated with no user action, and the token appears in no URL and in no browser storage,
- **AND** the document is served `no-store` with no validators, so the browser can never revalidate its way back to a previous daemon's token.

### Requirement: Serve the app for client-side routes but not for reserved roots
A path with no file behind it MUST be answered with the SPA document so the client-side router can
take over — but a path under a root the daemon's own surfaces own (`api`, `mcp`, `health`, `docs`,
`redoc`, `openapi.json`) MUST stay a real `404`. Answering those with `index.html` would turn every
stale endpoint and every client typo into a `200` full of HTML, which is far harder to debug than a
plain miss. The reserved roots MUST be matched by whole path segment and never by bare prefix, or
the UI's own `/mcp-servers` route stops resolving.

#### Scenario: a client-side route is served the app, an unknown API path is not
- **GIVEN** a daemon serving a built web UI,
- **WHEN** the browser requests `/mcp-servers` (a client-side route with no file on disk) and a client requests `/api/v1/nothing-here`,
- **THEN** the first is answered with the SPA document so the client-side router can take over, and the second is a genuine 404 rather than a 200 carrying a page of HTML.

### Requirement: Browse folders without reading files
The daemon MUST expose a read-only filesystem-browse operation (`GET /api/v1/fs/browse`) that,
given a directory path (defaulting to the user's home), returns that path, its parent, and its
immediate subdirectories. It MUST NOT return file contents and MUST be guarded by the same loopback
+ token auth as every other daemon route. See
[The Daemon Proxies OS File Actions](../../../docs/decisions/daemon-proxies-os-file-actions.md).

#### Scenario: the daemon browses a folder without revealing its files
- **GIVEN** a directory containing both subdirectories and files,
- **WHEN** `GET /api/v1/fs/browse` is called for it with a valid token,
- **THEN** the response names the resolved directory, its parent, and its immediate subdirectories only — no file is listed and no file's contents are read,
- **AND** the same call with no token is rejected.

### Requirement: Open the host's native folder picker
The daemon MUST expose ONE native OS dialog — the **folder** picker, `POST /api/v1/fs/pick-folder`
— so a web surface can open the host's real directory chooser instead of requiring a typed path. It
opens the host's native dialog (macOS `osascript`; Linux `zenity`/`kdialog`), invoked with a fixed
argument vector and no shell interpolation, and returns `{ available, path }`: `available=false`
when the host has no native dialog tool, `available=true` with `path=null` on cancel, otherwise the
chosen absolute path. It creates nothing and is guarded by the same loopback + token auth as every
daemon route. What a caller does when `available=false` is that caller's obligation — for the agent
config-dir flow, [agent-registry](../agent-registry/spec.md) "Offer a folder picker for a custom config directory".

Native open-file and save-file dialogs are not proxied: `POST /api/v1/fs/pick-file` and
`POST /api/v1/fs/save-file` do not exist. The browser already has both — `<a download>` saves a
file, and `<input type="file">` opens one and hands the page the file's contents rather than a path
the daemon must then read. A folder is the exception, because the browser deliberately withholds
absolute paths and registering an agent needs one.

#### Scenario: a native folder dialog reports its own absence
- **GIVEN** a host with no native folder-dialog tool,
- **WHEN** `POST /api/v1/fs/pick-folder` is called,
- **THEN** it answers `available: false` with a null path and creates nothing, so the caller can fall back to the in-app browser,
- **AND** on a host that has one, a cancelled dialog answers `available: true` with a null path, and a chosen directory answers its absolute path.

### Requirement: Open and reveal existing absolute paths
The daemon MUST expose filesystem-action operations: `POST /api/v1/fs/open` (open an existing
absolute path in an application — a `with` editor preference, or the OS default) and
`POST /api/v1/fs/reveal` (select / reveal an existing absolute path in the OS file manager). Both
MUST validate the path is absolute and exists before acting, MUST invoke the OS launcher with a
fixed argument vector and no shell interpolation, MUST create nothing, and MUST be guarded by the
same loopback + token auth as all other daemon routes. A non-absolute or non-existent path is
rejected (`FS_PATH_NOT_OPENABLE`, 400). Where a platform has no portable "select the file"
primitive (Linux), reveal degrades to opening the containing folder.

The daemon MUST also expose `GET /api/v1/fs/editors`, which enumerates common GUI editors detected
as installed on the host (macOS app-bundle names for `open -a`; Linux/Windows commands on `PATH`).
It returns each editor's display label and the launcher `value` accepted by `/fs/open`'s `with`,
reads nothing but app presence, and is guarded by the same loopback + token auth. It backs the
web-ui spec's preferred-editor setting, which every Open in editor uses — an agent's config files
([agent-registry](../agent-registry/spec.md) "Open config files in an external editor or reveal them"),
knowledge documents, memories, skill files and a conflicting sync file's copy — because Coffer edits
none of these files itself.

#### Scenario: a path that is not absolute is refused before anything is launched
- **GIVEN** a relative path, and an absolute path that does not exist,
- **WHEN** either is sent to `POST /api/v1/fs/open` or `POST /api/v1/fs/reveal`,
- **THEN** the request is rejected with `FS_PATH_NOT_OPENABLE` (400), no launcher process is started and nothing is created,
- **AND** `GET /api/v1/fs/editors` lists the GUI editors detected on this host, each with the launcher value that `/fs/open`'s `with` field accepts.

### Requirement: Write one bounded daemon log in one format
`~/.coffer/logs/daemon.log` MUST be the one file the daemon, the children it spawns, and every
surface writing on their behalf append to — one timeline rather than one file per writer, because
the question it answers is always "what else happened around then". The directory MUST be
relocatable through `COFFER_LOG_DIR` so a packaged or test install can put it elsewhere, and
`coffer path logs` MUST print the absolute path of the log directory and of `daemon.log` in it,
honouring that relocation, so a terminal or an agent can open or grep the file without knowing where
this install keeps it. The file
MUST be bounded by rotation rather than by deletion, and the retention sweep that ages out the
per-process and per-upstream log files MUST NOT delete it or its rotations: it is held open, and
deleting it would leave the daemon logging nowhere until the next restart.

Because several writers share it — Coffer's own structured JSON, other processes' uvicorn-style
lines, a rich-rendered upstream, some of it colour-escaped — the file is deliberately not one format, and every
reader of it is obliged to normalise rather than to assume (see "Serve the daemon log tail
normalised"). What the daemon *itself* writes, however, MUST be one format: every record produced
inside the daemon process — its own modules and the libraries logging alongside them, alembic and
asyncio included — MUST arrive as a single line carrying, at least, the instant the record was
created, its level, the logger that emitted it and the message, with a traceback kept inside the
record that raised it rather than spread across lines that state none of those. A library MUST NOT
be able to change that by configuring logging for its own purposes: the daemon owns its root logger
for its whole life, and any library configuration that would replace it is removed at the call site
rather than tolerated and parsed around; the daemon's own HTTP server is configured not to install
its own handlers, so its records take the same path. Each record MUST appear in the file exactly once — the file
is also the redirect target for the daemon's own stdout and stderr (see "Spawn a detached daemon
from any surface that needs one"), so a process writing to both that file and its stderr would
record everything twice and make one event read as two. Rotation MUST NOT strand the process's
own stdout and stderr in a rotated-away file: after each rollover they MUST follow to the new
`daemon.log`, so a traceback written straight to stderr stays readable where the reader looks.

#### Scenario: every line the daemon writes carries the same fields
- **GIVEN** a configured daemon, and a record emitted on an ordinary logger — one of Coffer's own modules, or a library's such as `alembic.runtime.migration` — after a migration has already run,
- **WHEN** `daemon.log` is read back,
- **THEN** that record is one line stating the instant it was created, its level, its logger and its message, and a record logged with an exception carries the traceback inside that same line rather than as lines stating none of those,
- **AND** the record appears exactly once, even though the detached daemon's own stderr is that same file.

#### Scenario: output written to stderr after a rotation lands in the current log
- **GIVEN** a detached daemon whose stderr is `daemon.log`, and a log that has just been rotated
- **WHEN** the process writes to stderr
- **THEN** the text is in `daemon.log` and in none of its rotations

#### Scenario: the command line names the daemon log file
- **GIVEN** an install whose log directory is relocated with `COFFER_LOG_DIR`, and a running daemon that has written to its log,
- **WHEN** the user runs `coffer path logs`, and `coffer path logs --json`,
- **THEN** both name the relocated directory and the `daemon.log` inside it as absolute paths, the second as a JSON object,
- **AND** the named `daemon.log` exists and is the file the daemon is writing to.

### Requirement: Serve the daemon log tail normalised
`GET /api/v1/daemon/logs` MUST return the tail of that file, newest-first, guarded by the token even
though `/daemon/status` on the same router is not: a readiness probe is public, log contents are
not. It MUST accept `since`, a severity floor (`level`), the older `errors_only` boolean, and a
bounded `limit`, and MUST read from the tail rather than the head so a large file is never pulled
into memory whole. Every record MUST carry the timestamp, level and logger its line actually
stated, whichever writer produced it; escape sequences MUST be stripped; continuation lines such as
a traceback MUST ride with the record that raised them; and a line no format fits MUST be kept whole
rather than dropped, because it is often the interesting one. The answer MUST also carry `path`,
the absolute path of the file the tail was read from — also when that file does not exist yet — so
the Activity page's Daemon log tab can name the file it shows and open it through
`POST /api/v1/fs/open`.

`coffer log daemon [--since <when>] [--errors] [--limit <n>] [--json]` MUST read the same tail
through that route — the one the Activity page reads — so a terminal sees the same normalised
records the page shows: `--since` and `--limit` pass through, `--errors` narrows to errors, the
table form prints one record per entry with its time, level, logger and message, and `--json`
prints the records as the route returns them. A refusal from the route MUST be printed with the
route's error and a non-zero exit.

#### Scenario: the daemon log tail reads every writer's format
- **GIVEN** a `daemon.log` holding Coffer's own structured JSON, a uvicorn-style line from another process, a `LEVEL - logger - message` line from an upstream, a colour-escaped line from an upstream, and a multi-line traceback,
- **WHEN** `GET /api/v1/daemon/logs` is called with a token,
- **THEN** the response is newest-first and bounded by `limit`, every record carries the time, level and logger its line actually stated, escape sequences are stripped, the traceback rides with the record that raised it, and a line no format fits is kept whole rather than dropped,
- **AND** `level` and `since` narrow the window, while the same call with no token is rejected even though `/daemon/status` on the same router is open.

#### Scenario: the daemon log tail names the file it read
- **GIVEN** a daemon whose log directory holds `daemon.log`, and one whose log directory holds none yet
- **WHEN** `GET /api/v1/daemon/logs` is called with a token on each
- **THEN** both answers carry `path`, the absolute path of that directory's `daemon.log`, the second with no records

#### Scenario: the command line reads the daemon log tail
- **GIVEN** a running daemon whose `daemon.log` holds an info record, an error record carrying a traceback, and a record older than one hour,
- **WHEN** the user runs `coffer log daemon --json --since 1h`, then `coffer log daemon --errors --limit 1`,
- **THEN** the first prints, newest-first, the two recent records exactly as `GET /api/v1/daemon/logs` returns them for that window, the older record absent,
- **AND** the second prints only the error record, with its traceback riding with it.

### Requirement: Install the console scripts from source
Installing from source (`pip install ./backend`) MUST place the `coffer` CLI and the
`coffer-mcp-shim` stdio entry point on the user's `PATH` as console scripts, so the daemon and shim
are usable with no separate deployment step. See
[PyInstaller Distribution](../../../docs/decisions/distribution-pyinstaller.md).

#### Scenario: a source install puts the CLI and the shim on PATH
- **GIVEN** the backend package's install metadata,
- **WHEN** it is installed from source,
- **THEN** it declares `coffer` and `coffer-mcp-shim` as console scripts,
- **AND** each resolves to a callable entry point in the installed package, so both run with no further deployment step.

### Requirement: Release the macOS arm64 terminal archive
The release pipeline MUST produce, per `v*` tag, the **terminal-install tier** for **macOS arm64
only**: a `coffer-cli-<triple>.tar.gz` archive containing exactly four binaries: `coffer` (the
management CLI), `coffer-daemon`, `coffer-mcp-shim` and `coffer-seatalk-bridge` (the executable
that loads the SeaTalk SDK on the daemon's behalf, see [channels/seatalk](../channels/seatalk/spec.md)
"Load the websocket client library from an operator-supplied directory"), plus `coffer-mcp-shim-lib/`,
the folder of libraries the one-folder shim loads from beside itself (see
[ADR distribution-pyinstaller](../../../docs/decisions/distribution-pyinstaller.md)). The binaries MUST stay co-located inside the archive so the frozen resolution
of "Spawn a detached daemon from any surface that needs one" finds `coffer-daemon` next to
`coffer`. macOS x64 (Intel), Linux and Windows are deliberately not built — those legs were never
validated end to end. This archive carries the "no system Python required" promise on its own: on a
machine with no system Python, extracting it and running `coffer daemon start` reaches
`status: ready`, and the daemon serves the UI, which renders authenticated at the origin `daemon.json` names. Both tiers ship per tag: this
archive is the terminal install, and the `.dmg` of [desktop-app](../desktop-app/spec.md) "Ship the desktop tier as a macOS arm64 dmg" is the double-click one;
neither is a substitute for the other.

#### Scenario: release tag produces the CLI archive and SHA256SUMS
- **GIVEN** a release tag matching `v*` is pushed,
- **WHEN** the release workflow finishes,
- **THEN** the release contains the terminal tier — `coffer-cli-<triple>.tar.gz` for macOS arm64, holding `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-seatalk-bridge`, co-located with the shim's `coffer-mcp-shim-lib/` folder, and no other binary,
- **AND** the release contains a single aggregated `SHA256SUMS` file covering every artifact of every tier, including the desktop tier of [desktop-app](../desktop-app/spec.md) "Ship the desktop tier as a macOS arm64 dmg",
- **AND** no other platform is built.

### Requirement: Publish one aggregated checksum file
The release pipeline MUST produce one aggregated `SHA256SUMS` file — generated in CI and
concatenated across matrix legs in the release job — covering every artifact of every tier, so
downloaders can verify integrity without trusting the GitHub Release UI alone.

#### Scenario: one checksum file verifies every artifact of every leg
- **GIVEN** two matrix legs whose `artifacts/` directories each hold release files,
- **WHEN** each leg runs the workflow's checksum step and the release job stages the legs' outputs,
- **THEN** the release holds exactly one `SHA256SUMS`, listing every staged artifact exactly once,
- **AND** every artifact verifies against it with a stock SHA-256 checker.

### Requirement: Deploy frozen sibling binaries and back up the history database before migrating
When the daemon detects that it is running as a frozen build, it MUST idempotently deploy its
sibling binaries — `coffer`, `coffer-daemon`, `coffer-mcp-shim` — into
`~/.coffer/bin/` at startup. `coffer` is in that list so that a user who installed only the desktop
tier has the management CLI on disk after the first launch, and `coffer-daemon` so the frozen shim
can resolve it as a sibling. The shim is a one-folder build: its library folder,
`coffer-mcp-shim-lib/`, MUST be deployed with it into the same version directory, before the
executable, and a version directory whose shim lacks that folder MUST be deployed again. The
daemon finds each sibling beside itself or, in the desktop app, in `Contents/Resources`, where the
app keeps the shim. Each build MUST land in its own `~/.coffer/bin/<version>/` directory,
with the public `~/.coffer/bin/<name>` paths being symlinks into it that are flipped atomically, so
that a deploy never overwrites a binary in place and the previous version's directory stays on disk
for a rollback (the two newest version directories are kept; older ones are pruned). The copy MUST
be atomic (temp sibling in the same directory, executable bit set, then rename, with the version
sentinel written last) so that a crash or a concurrently executing binary never observes a truncated
file, and staleness MUST be decided by two signals — byte size and the version sentinel — never
mtime, which says when a build was extracted rather than what it contains. A deploy MUST also
remove every public `~/.coffer/bin/<name>` symlink that points into a version directory under a
name this build does not ship, so a binary a release dropped stops resolving to an old build
instead of lingering on the user's `PATH`; anything at such a path that is not a symlink into a
version directory is not Coffer's deployment and MUST be left alone.

Before `alembic upgrade head` changes the on-disk history database, `~/.coffer/runs.db`, the
daemon MUST write a copy of it to `runs.db.pre-<revision>` with `VACUUM INTO`: one self-contained
file holding a consistent snapshot of its live data, including what its write-ahead log still
holds, without its free pages and without `-wal`/`-shm` companions. It keeps the three newest
copies, never overwrites an earlier copy, removes a copy that failed half-way and does not migrate
without one; an already-current schema or an in-memory database MUST NOT be copied.
A source install MUST NOT do
any of this: `pip install` already puts the console scripts on `PATH` (see "Install the console
scripts from source"). The daemon owns the deployment because it is the one process every frozen install starts,
whichever tier it came from.

#### Scenario: a frozen daemon deploys its sibling binaries on start
- **GIVEN** a frozen `coffer-daemon` started from an extracted release archive, with `coffer` and `coffer-mcp-shim` beside it,
- **WHEN** the daemon starts,
- **THEN** each sibling binary is reachable and executable at `~/.coffer/bin/<name>` — a symlink into `~/.coffer/bin/<version>/`, where the file was copied atomically through a temp sibling and a rename, and the symlink itself was flipped atomically,
- **AND** a second start with nothing changed leaves those files untouched, while a version change deploys the new build into its own `<version>/` directory and re-points the symlinks — as decided by the byte-size and version-sentinel staleness check — keeping the previous version's directory on disk so the upgrade can be undone by pointing the links back; only the two newest version directories are kept.

#### Scenario: a deploy removes the link of a binary the build no longer ships
- **GIVEN** `~/.coffer/bin/coffer-callback` is a symlink into a version directory an earlier build deployed, and a frozen `coffer-daemon` whose build ships only `coffer`, `coffer-daemon` and `coffer-mcp-shim`,
- **WHEN** the daemon starts and deploys its siblings,
- **THEN** `~/.coffer/bin/coffer-callback` no longer exists, while `coffer`, `coffer-daemon` and `coffer-mcp-shim` point into the new build's version directory,
- **AND** a regular file at `~/.coffer/bin/<name>` for a name the build does not ship is left untouched.

#### Scenario: a schema upgrade keeps a copy of the history database
- **GIVEN** a daemon starting against a `runs.db` whose Alembic revision is behind this build's head,
- **WHEN** the migrations run at startup,
- **THEN** `runs.db.pre-<revision>` holds the pre-upgrade state beside the live file as one file, with what the write-ahead log held and none of the free pages, only the three newest such copies are kept, and a start against an already-current schema — or an in-memory database — copies nothing.

#### Scenario: the shim's library folder is deployed with it
- **GIVEN** a frozen `coffer-daemon` whose build holds `coffer-mcp-shim` with its `coffer-mcp-shim-lib/` folder, beside the daemon or in the app's `Contents/Resources`
- **WHEN** the daemon starts
- **THEN** `~/.coffer/bin/<version>/` holds the shim with `coffer-mcp-shim-lib/` beside it, and `~/.coffer/bin/coffer-mcp-shim` starts from there
- **AND** a later start finding that version's folder missing deploys the shim again

### Requirement: Clear inherited agent-home variables at start
In a signed build the daemon MUST also drop the inherited proxy and certificate settings from its own environment
at start (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, `SSL_CERT_FILE`, `SSL_CERT_DIR`, `REQUESTS_CA_BUNDLE`,
`CURL_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS`, in either case) and use the macOS system proxy and keychain instead, as
[secret](../secret/spec.md) "Keep the master key behind a storage port chosen by the build" states; the model proxy
does the same at its own start.

The daemon MUST remove `CLAUDE_CONFIG_DIR` and `CODEX_HOME` — every agent type's home variable — from its own environment when it starts, before it spawns anything, and log once which ones it removed. A daemon started from a shell that exports one would otherwise hand it to every agent process it spawns, so an agent registered on the default directory would run against the exported one while Coffer delivers its skills, MCP entry and config into the default. An agent gets the variable only from its own registered config directory ([agent-registry](../agent-registry/spec.md)), set on that agent's process alone.

#### Scenario: a daemon started from a shell exporting an agent home does not pass it on
- **GIVEN** a shell that exports `CLAUDE_CONFIG_DIR` and `CODEX_HOME`
- **WHEN** the daemon is started from it
- **THEN** the daemon's environment holds neither variable and the daemon log names both once
- **AND** a turn for an agent on its default directory is spawned with neither variable, while an agent with a custom directory gets its own directory in its type's variable

### Requirement: Supervise the model proxy from the daemon
The daemon MUST supervise the local model proxy as its one sibling process, started from the
daemon's own binary in proxy mode (`coffer-daemon proxy`): at start it re-attaches to a running
proxy of the same version found through `~/.coffer/proxy.json` (`port`, `pid`, `started_at`,
`version` and a control token, mode `0600`) — after checking that it is Coffer's (below) — asks a proxy of another version to drain and replaces
it once it exits, and spawns one when none is running; it health-checks the proxy on a short period
and restarts it after a crash. It pushes the proxy what it serves — the agents' token digests and
each agent's route with the decrypted keys, held only in the proxy's memory — over the proxy's
authenticated loopback control route after every reconcile pass that could have changed it — every
pass but a periodic one that wrote nothing, failed no new target and left the same differences
open — and whenever a token changes. The
daemon stopping or restarting MUST NOT stop the proxy, so agents' in-flight model streams outlive a
daemon upgrade. `GET /api/v1/proxy/status` reports whether it runs, its
port, pid, version, restart count and last error.

`proxy.json` and the loopback port are writable by any process of the same user, and the push
carries the provider keys, so the daemon MUST know a proxy is its own before it pushes anything.
It derives an attest key from the master key (context `coffer-proxy-attest-key/v1`) and hands it
to the proxy it spawns on the child's standard input, never in its arguments or environment. Before
every `/_coffer/state` push, and before re-attaching to a proxy found through `proxy.json`, it
challenges `POST /_coffer/attest` with a fresh nonce and accepts only an answer that is the
HMAC-SHA256 of the nonce and the proxy's own port under that key. A process that fails the
challenge, or a proxy that holds no key, MUST be sent nothing and is logged as
`model_proxy.attest_failed`: the daemon does not attach to it, reports the reason as the proxy's last error, and never sends it a key.

#### Scenario: the daemon restarts a crashed proxy
- **GIVEN** a supervised proxy
- **WHEN** the proxy process is killed
- **THEN** the supervisor spawns a new one on the same port, pushes it the current state, and counts the restart

#### Scenario: a daemon restart re-attaches to the running proxy
- **GIVEN** a proxy started by an earlier supervisor that has since stopped
- **WHEN** a new supervisor starts
- **THEN** it attaches to the same proxy process rather than spawning another

#### Scenario: a periodic pass that changes nothing tells no pass listener
- **GIVEN** a reconciler with a pass listener, whose first periodic pass found a difference it only reports
- **WHEN** a second periodic pass finds the same difference and writes nothing
- **THEN** the listener is not called for it
- **AND** a hinted pass, a periodic pass that repairs drift, and a periodic pass after which a difference closed are each heard

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

### Requirement: Hand an upgrade of Coffer to an agent
The desktop shell checks for and installs updates itself. A browser has
nothing to install with, and how a copy of Coffer is upgraded depends on how it
was installed, so the daemon MUST answer the token-gated
`GET /api/v1/daemon/upgrade` with the install method it detects — `binaries`
(the installer's or a release archive's frozen binaries), `app` (the macOS
desktop app) or `source` (a source checkout) — and a `handoff` prompt for the
person's agent. The prompt MUST name the running version,
the install method with the daemon's executable (and the checkout for a source
run), the machine, and the install page's Upgrade section, and MUST tell the
agent to keep `~/.coffer` exactly as it is, to restart the daemon, and to
confirm with `coffer --version` and `coffer daemon status` that both report the
new version. For the installer's binaries it MUST say that `coffer update` does
the upgrade and the restart. It carries the standing rules of every hand-off.

#### Scenario: the upgrade hand-off names how this copy was installed
- **GIVEN** a daemon running Coffer 0.3.1 from the installer's frozen binaries
- **WHEN** `GET /api/v1/daemon/upgrade` is read
- **THEN** the answer's install method is `binaries` and its prompt names 0.3.1, the executable, the machine, `coffer update` and the install page's `#upgrade` section
- **AND** the prompt says to keep `~/.coffer` and to verify with `coffer --version` and `coffer daemon status`

### Requirement: Report the state the shell shows
The daemon's state MUST be visible to the user while starting it stays automatic. Every fact the
web UI's Settings → Daemon tab and its About tab show about the daemon —
lifecycle phase, bound port, start time, version, executable, process id, the
commit a release build was stamped with, Coffer's data folder and how many agents carry Coffer's
connection — MUST come from
`GET /api/v1/daemon/status` (see "Answer the status probe without a token"), so the page can show a
daemon's state without a token and without a route of its own, and so the footer, the Daemon tab,
`coffer daemon status` and the desktop shell's version check all read one answer. The one daemon
setting those surfaces also show, whether it starts at login, comes from
`GET /api/v1/daemon/residency` (see "Change residency from the settings page or the command line"). Showing the state MUST NOT move starting the daemon onto the user: every surface that needs
a daemon and finds none still starts one itself (see "Spawn a detached daemon from any surface that
needs one").

#### Scenario: the status probe carries what the shell shows
- **GIVEN** a running daemon,
- **WHEN** `GET /api/v1/daemon/status` is called with no token,
- **THEN** the response carries the phase, port, start time, version, executable, channel, pid, commit, data folder and connected-agent count Settings → Daemon and About show,
- **AND** `coffer daemon status --json` reports the same version, channel and port.

### Requirement: Report what Coffer stores and clear the rebuildable cache
The daemon MUST report, for Settings › Data, what Coffer keeps on this machine in the four kinds
of [Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md)
the user acts on, through `GET /api/v1/storage`: the **vault** (the vault repository
`~/.coffer/vault/`, a git repository whether or not it syncs — its path, its size with its
history and how many versions it holds; no version count before the repository has been created), the
**local content** (channel media under `~/.coffer/content/`, which never sync:
their locations, the one folder to open, and their size), the **history** (the database file
holding the records, `~/.coffer/runs.db` unless `COFFER_DB_URL` names another, with its WAL, and
its size together with the log directory's, `~/.coffer/logs/` unless `COFFER_LOG_DIR` names
another, and with the skills' working files in `~/.coffer/skill-data/` and the config backups in `~/.coffer/config-backups/`) and the **rebuildable cache** (the memory tree under
`~/.coffer/derived/`, and its size). Every path MUST come from the same place its owner
resolves it, so an override the owner honours is honoured here.

`POST /api/v1/storage/cache/clear` MUST delete the files of the memory tree, and nothing else: no vault, local content, history or other file
under `derived/`, and no partition row, so the next memory update rebuilds each partition from the
agents' own memory. It MUST be refused (`UPKEEP_ALREADY_RUNNING`) while a memory pass is running,
because that pass is writing into the tree, and MUST record the clear in the audit log with the
bytes freed.

#### Scenario: the storage summary reports the four kinds
- **GIVEN** a vault repository of three commits, channel media, a database with its WAL and a memory tree
- **WHEN** `GET /api/v1/storage` is called
- **THEN** it reports the vault as `~/.coffer/vault` with 3 versions, the local content with the channel media location under `~/.coffer/content` and its size, the history as `runs.db` with its WAL plus the log directory, `skill-data` and `config-backups`, and the cache as the size of the memory tree
- **AND** before the vault repository has been created it reports the vault with no version count

#### Scenario: clearing the cache leaves everything else
- **GIVEN** a memory tree, a knowledge document in the vault, channel media, a sync round's hand-merge copy and the database
- **WHEN** `POST /api/v1/storage/cache/clear` is called
- **THEN** the memory tree is empty, everything else is untouched, the answer carries the bytes freed and the audit log records the clear
- **AND** while a memory pass is running the clear is refused and nothing is deleted

### Requirement: Supervise every background task the daemon starts
Work the daemon starts to run beside the call that started it — a channel
adapter's inbound loop, a channel or chat turn, a periodic worker, a
fire-and-forget write — MUST run under one task supervisor rather than as a
bare `asyncio` task, because a bare task that raises dies silently: the
exception surfaces only if something later retrieves it. The supervisor MUST
give every task a name, and when a task ends by raising it MUST write one
`runtime.task.crashed` line to `daemon.log` carrying the task's name and the
exception with its traceback at that moment, and count the crash. A task MUST
be restarted after a crash only when its owner asked for that, with a backoff
that doubles from one second up to a cap; a clean return ends it. Each channel
adapter's inbound loop — a Telegram channel's long poll, a SeaTalk channel's
websocket supervisor — MUST be restarted on its own, so one adapter's crash
never stops or restarts another channel; the SeaTalk websocket's blocking
listen call keeps its own thread (spec
[channels/seatalk](../channels/seatalk/spec.md) "Receive every event over one
outbound websocket connection"). At shutdown, after every owner has stopped
its own work in the teardown's order, the supervisor MUST cancel whatever is
still running, bounded so a task that ignores cancellation cannot hold the
daemon up (see "Shut down through one graceful exit path"). A task the same
function awaits or cancels before it returns — the two sides of an
`asyncio.wait` race, a shielded write — is not background work; the lint gate
`scripts/check_bare_tasks.py`, run by `make lint`, MUST refuse any other bare
`create_task` or `ensure_future` outside the supervisor and MUST name each
allowed one, per file, with the reason it is awaited in place.

#### Scenario: a background task that crashes is logged with its name
- **GIVEN** a supervised task named `telegram-poll:family`
- **WHEN** it raises `RuntimeError`
- **THEN** `daemon.log` receives one `runtime.task.crashed` line naming `telegram-poll:family`, the exception class and its traceback
- **AND** the daemon's crash count goes up by one

#### Scenario: a crashed channel adapter restarts without touching the others
- **GIVEN** two running Telegram channels, each polling in its own supervised loop
- **WHEN** the first channel's loop raises an error its own retry ladder does not catch
- **THEN** the crash is logged under that channel's task name and its loop runs again after the backoff
- **AND** the second channel's loop keeps running and is never restarted

#### Scenario: shutdown cancels the background tasks still running
- **GIVEN** supervised tasks still running when the daemon shuts down
- **WHEN** the teardown reaches the supervisor's sweep
- **THEN** every one of them is cancelled, and none is counted as a crash

#### Scenario: a new bare background task fails the lint gate
- **GIVEN** a module under `backend/coffer/` that starts a task with `asyncio.create_task` and is not on the gate's allow-list
- **WHEN** `scripts/check_bare_tasks.py` runs
- **THEN** it fails and names the file, pointing at the supervisor's `spawn`
- **AND** an allow-list entry for more calls than a file makes fails too, as stale

### Requirement: Report event-loop lag and background task crashes on the status
The daemon MUST sample how late its event loop wakes a periodic probe and keep
the samples for a rolling window, because a synchronous call that blocks the
loop stalls every request, channel and turn at once and is otherwise visible
only as general slowness. `GET /api/v1/daemon/status` MUST carry a `runtime`
block with the window's 99th-percentile and maximum lag in milliseconds (null
before the first sample), the number of samples and the window's length, the
number of supervised tasks running, the number of background task crashes
since the daemon started, and the most recent crash's task name, exception
class, time and whether it was restarted. The crash's exception message MUST
NOT appear there — the probe answers without a token, and a message can carry
what it failed on — only in `daemon.log`. `coffer daemon status` MUST print the
lag and the task counts, and `--json` MUST carry the `runtime` block as the
route answers it.

#### Scenario: the status reports loop lag and task crashes
- **GIVEN** a running daemon whose probe has taken a sample, and a supervised task that has crashed with `LookupError`
- **WHEN** `GET /api/v1/daemon/status` is called with no token
- **THEN** its `runtime` block carries the lag's p99 and maximum over a 300-second window, the tasks running and the crash count including that crash
- **AND** `last_crash` names the task and `LookupError`, and the exception's message is nowhere in the block

#### Scenario: the command line prints loop lag and task crashes
- **GIVEN** a running daemon whose probe has taken a sample
- **WHEN** the user runs `coffer daemon status`, and `coffer daemon status --json`
- **THEN** the first prints a `loop lag:` line with the p99 and maximum and the window, and a `tasks:` line with the running and crashed counts
- **AND** the second carries the route's `runtime` block

### Requirement: Hand a daemon error about the environment to an agent
A record of `GET /api/v1/daemon/logs` that is an ERROR (or CRITICAL) whose message
or folded lines show a cause outside Coffer — a refused or reset connection, a
timeout, a name that does not resolve, a certificate error, a missing or
unreadable file or program — MUST carry `handoff`: a prompt with the logger, the
message and the traceback, every line passed through the secret scrub, and this
machine, asking for the cause and a proposed fix before anything changes. Every
other record — a warning, an error with no such cause — carries none.

#### Scenario: an environment error carries a hand-off and an internal one does not
- **GIVEN** a daemon log holding an ERROR about a refused connection with a traceback, an ERROR that is a Coffer `KeyError`, and a warning that mentions a refused connection
- **WHEN** the log is read
- **THEN** only the first carries a `handoff`, and it quotes the logger, the message and the traceback

### Requirement: Wait in a setup state when git is missing or too old
The vault is a git repository and every sync round's merge needs git 2.40, so
git is a hard dependency. Before it opens the vault the daemon MUST look for a
git of version 2.40 or later, first on its own `PATH`, then on the `PATH` the
person's login shell reports; a git good enough only on the login shell's
`PATH` MUST be used, by putting its directory first on the daemon's `PATH`.

Without one the daemon MUST still start and serve, in a **setup state**: it
serves the web UI, publishes its token and port as every start does, and wires
nothing that touches the vault — no migrations, vault, kinds, workers or MCP
sessions. `GET /api/v1/daemon/status` MUST report `status: "setup"` and a
`setup` object: `need: "git"`, `reason` (`git_missing` when no git was found,
`git_too_old` naming the newest version found as `found`), `needed` (`2.40`),
a `message` saying what is wrong, that the vault keeps its history and syncs
with git, and what to do, and `handoff`, the prompt asking the person's agent
to install or update git — naming the machine and no installer, as the other
git hand-offs do. Every other API route and `/mcp` MUST answer 503
`GIT_NEEDED` with that message and, in `details`, the reason, the versions and
the hand-off — except the status, `POST /api/v1/daemon/setup/check`,
`/daemon/restart` and `/daemon/shutdown`.

`POST /api/v1/daemon/setup/check` MUST look for git again, both `PATH`s, never
from a cached answer, and answer `ready: true` once a usable git is there (a
login-shell git is put first on the daemon's `PATH`, so a restart's successor
inherits it), or `ready: false` with the current `setup`. A restart then starts
the daemon normally. A `coffer` command that needs the daemon MUST print the
message and the hand-off and exit 10 instead of sending its request; `coffer
daemon status` MUST report the state and the same words, and `coffer daemon
start` MUST say them once the daemon answers. The MCP shim MUST pass a
refusal's message and hand-off to the agent whole.

#### Scenario: a machine without git starts the daemon in its setup state
- **GIVEN** a machine with no `git` on the daemon's `PATH` or the login shell's
- **WHEN** the daemon starts
- **THEN** it serves, and `GET /api/v1/daemon/status` reports `status: "setup"` with `reason: "git_missing"`, `needed: "2.40"` and a prompt asking an agent to install git that names no installer
- **AND** no vault repository was created

#### Scenario: a git older than 2.40 puts the daemon in its setup state with a hand-off
- **GIVEN** a machine whose only `git` reports version 2.30
- **WHEN** the daemon starts
- **THEN** the status reports `reason: "git_too_old"`, `found: "2.30"` and `needed: "2.40"`
- **AND** its hand-off asks an agent to update git and confirm with `git --version`, and names no installer

#### Scenario: a git only on the login shell's PATH is used
- **GIVEN** a daemon whose own `PATH` has git 2.30 and a login shell whose `PATH` has git 2.45
- **WHEN** the daemon looks for git
- **THEN** it uses the login shell's git, whose directory comes first on the daemon's `PATH`

#### Scenario: the setup state refuses what needs the vault
- **GIVEN** a daemon in its setup state
- **WHEN** an API route that needs the vault, or `/mcp`, is called
- **THEN** it answers 503 `GIT_NEEDED` with the setup message, and `details` carry the reason and the hand-off
- **AND** the status, Check again, restart and shutdown routes still answer

#### Scenario: check again finds git and the restart finishes the start
- **GIVEN** a daemon in its setup state, on a machine where git 2.45 has since been installed
- **WHEN** `POST /api/v1/daemon/setup/check` is called
- **THEN** it answers `ready: true`
- **AND** with git still missing it answers `ready: false` and the current setup state

#### Scenario: a command that needs the daemon prints why it waits
- **GIVEN** a daemon in its setup state
- **WHEN** a `coffer` command that needs the daemon runs
- **THEN** it prints the setup message and the hand-off prompt and exits 10, sending no request of its own
- **AND** `coffer daemon status` prints `status: setup` with the same message and exits 0

### Requirement: Open an agent session in a terminal
The daemon MUST expose `POST /api/v1/fs/terminal`, which starts an agent's session
in a terminal window on the host — an existing session resumed, a new session
begun with a prompt, or a blank new session. The body is `{terminal, agent, cwd, resume? | prompt?}`: `terminal` is a
launcher value from `GET /api/v1/fs/terminals`, a custom command template, or null for the
system terminal; `agent` is `claude_code` or `codex`; `cwd` is an absolute directory; and
at most one of `resume` (a session id) or `prompt` (the first message of a new session) is
given — neither starts a new session with no first message. The daemon builds the command itself and the client never sends a command line: a
resume runs `cd '<cwd>' && claude --resume <id>` or `codex resume <id>`; a new session runs
`claude "$(cat '<file>'; rm -f '<file>')"` (`codex` alike), where the prompt was written to a
private temporary file (mode `0600`, under `~/.coffer/tmp/handoff/`) that the command reads and
removes, so the prompt's text never appears on a command line or in shell history; a blank
session runs `cd '<cwd>' && claude` (`codex`) with no argument. A session id MUST be
checked against `[A-Za-z0-9-]` before it reaches a command. A `cwd` that is absent, or that no longer
exists as a directory, runs in Coffer's default workspace `~/.coffer/content/workspace` (created
on first use) instead of failing.

The terminal is started by one small adapter per launcher, each invoked with an argument vector and no
shell of the daemon's: Terminal.app and iTerm through `osascript`; Warp through a launch configuration
file opened with `open warp://launch/<file>`; Orca through its command line; on Linux `gnome-terminal`,
`konsole` or `x-terminal-emulator` running `sh -lc <command>`; null is the system terminal (Terminal.app
on macOS, `x-terminal-emulator` on Linux). A custom template is split into arguments with
shell-word rules, `{cwd}` and `{command}` are substituted inside each argument, and the result is run as an
argument vector, never through a shell; a template without `{command}` is invalid.

An unknown `agent`, a session id that fails the check, a relative `cwd`, both `resume`
and `prompt`, or an invalid template MUST be refused `FS_TERMINAL_INVALID` (400) before anything is started;
a launcher that cannot be started is `FS_TERMINAL_FAILED` (502) carrying its reason. The route is guarded by the
same loopback + token auth as every daemon route. Its caller is the web UI's hand-off, session
rows and New conversation ([web-ui](../web-ui/spec.md) "Let the user choose a terminal"; [chat](../chat/spec.md)
"Open a conversation in the terminal").

#### Scenario: a resume opens the agent's resume command in the session's directory
- **GIVEN** an existing directory `/work/api` and no terminal chosen
- **WHEN** `POST /api/v1/fs/terminal` is called with agent `claude_code`, that `cwd` and `resume` `abc-123`
- **THEN** the system terminal's launcher is started with an argument vector carrying `cd '/work/api' && claude --resume abc-123`
- **AND** the same call for `codex` carries `codex resume abc-123`

#### Scenario: a prompt never appears on a command line
- **GIVEN** a prompt whose text is "rotate the key sk-test"
- **WHEN** it is sent with `prompt` for a new Claude Code session
- **THEN** the launcher's argument vector carries `cat` of a temporary file and not the prompt's text
- **AND** that file holds the prompt, is readable by its owner only, and is removed by the command that reads it

#### Scenario: an unsafe session id is refused before anything starts
- **GIVEN** a `resume` of `abc;touch /tmp/x`
- **WHEN** it is sent
- **THEN** the answer is `FS_TERMINAL_INVALID` (400) and no launcher is started
- **AND** so are an unknown agent, a relative `cwd`, and a body with both `resume` and `prompt`

#### Scenario: a body with neither resume nor prompt starts a blank session
- **GIVEN** an existing directory `/work/api`
- **WHEN** `POST /api/v1/fs/terminal` is called with agent `codex`, that `cwd` and neither `resume` nor `prompt`
- **THEN** the launcher is started with an argument vector carrying `cd '/work/api' && codex` and nothing after it

#### Scenario: a custom template runs as an argument vector
- **GIVEN** a terminal value `mycli --dir {cwd} -- {command}`
- **WHEN** a resume is sent
- **THEN** the launcher is started with the arguments `mycli`, `--dir`, the directory, `--` and the command, with no shell involved
- **AND** a template without `{command}` is refused `FS_TERMINAL_INVALID`

#### Scenario: a missing directory opens in the default workspace
- **GIVEN** a `cwd` that no longer exists
- **WHEN** a resume is sent
- **THEN** the terminal opens in `~/.coffer/content/workspace`, created if need be

#### Scenario: the terminal route needs the token
- **GIVEN** a call with no token
- **WHEN** `POST /api/v1/fs/terminal` is called
- **THEN** it is rejected and nothing is started

### Requirement: List the terminals installed on this host
The daemon MUST expose `GET /api/v1/fs/terminals`, which enumerates common terminal applications
detected as installed on the host (macOS app-bundle names; Linux commands on `PATH`). It returns each
terminal's display label and the launcher `value` that `POST /api/v1/fs/terminal` accepts as `terminal`,
reads nothing but the presence of the application, starts nothing, and is guarded by the same loopback + token
auth. It is the terminal counterpart of `GET /api/v1/fs/editors`
("Open and reveal existing absolute paths"); its consumer is the web UI's preferred-terminal setting
([web-ui](../web-ui/spec.md) "Let the user choose a terminal").

#### Scenario: the daemon lists the terminals installed on this host
- **GIVEN** a host with two supported terminals installed
- **WHEN** `GET /api/v1/fs/terminals` is called with a valid token
- **THEN** it lists those two with their labels and the launcher values `POST /api/v1/fs/terminal` accepts, and nothing is started
- **AND** the same call with no token is rejected

### Requirement: Change residency from the settings page or the command line
The one residency setting — whether the login service is installed (see "Run as a login service")
— MUST be readable and settable over REST, from Settings → Daemon and with `coffer daemon residency show` / `set`. The daemon never stands down on
its own: once started it serves until it is stopped, or until another daemon supersedes it (see
"Stand down only when provably superseded"), so there is no idle window to configure.

`GET /api/v1/daemon/residency` MUST report whether a login service is supported on this host and
whether it is installed. `PUT` on the same route MUST install or remove it, and the change MUST take
effect at once, because the system's service manager is a different process. On a host with no
login service, a request to install one MUST leave it off and say so rather than fail. The response
MUST report what is true after the change, and the change MUST be audited as
`daemon_residency_updated` with that same value.

The port is changed with `coffer config set daemon.port` because a port is changed when the daemon
cannot start; residency is a settings question asked of a daemon that is working, so its commands
call the route above, and no command installs or removes the login service any other way or sets an
idle window.

#### Scenario: the settings page changes residency in one request
- **GIVEN** a running daemon on a host that supports a login service, with nothing configured,
- **WHEN** a client reads `GET /api/v1/daemon/residency` and then sends `PUT /api/v1/daemon/residency` with `login_service_installed: true`,
- **THEN** the read reports a supported login service that is not installed, and the login service is installed at once,
- **AND** the response and a `daemon_residency_updated` audit entry both report `login_service_installed: true`, and neither carries an idle window.

#### Scenario: residency is set in Settings or on the command line
- **GIVEN** a host that supports a login service
- **WHEN** the command tree is listed, and the user runs `coffer daemon service install` and `coffer daemon idle`
- **THEN** residency is `coffer daemon residency show` and `set`, which call the route above
- **AND** the old `service` and `idle` subcommands exit non-zero as unknown commands, writing nothing

### Requirement: Check the installed binaries for a new release
A daemon running from the installer's frozen binaries MUST check for a newer
release of Coffer one minute after it starts and then every 24 hours, so a
machine without the desktop app learns that a release exists. The check MUST
be one read-only `GET` of the GitHub API's latest release for the project,
bounded in time and size and sending nothing about the user; a failure keeps the
last result and is logged once per failure streak. `update_check` in
`~/.coffer/daemon-config.json` (the Check automatically switch on Settings ›
About) MUST turn the periodic check off, and `COFFER_UPDATE_CHECK=off` MUST pin
it off. A daemon running from the desktop app or from source MUST NOT check:
the app checks for itself and a source checkout is upgraded with git.

`GET /api/v1/daemon/upgrade` MUST report, beside the install method and the
hand-off, whether this daemon checks, whether the switch is on, when it last
checked successfully, the last failure, and the newest release found — its
version, release notes, publication date and page — when it is newer than the
running version. `POST /api/v1/daemon/upgrade/check` MUST check now and answer
the same record; `PUT /api/v1/daemon/upgrade/auto-check` MUST set the switch.

#### Scenario: the daemon reports a newer release of its binaries
- **GIVEN** a daemon running Coffer 0.3.0 from the installer's binaries, and a latest release v0.4.0
- **WHEN** `POST /api/v1/daemon/upgrade/check` is called
- **THEN** `GET /api/v1/daemon/upgrade` reports 0.4.0 with its notes and the time of the check

#### Scenario: the app's daemon leaves checking to the app
- **GIVEN** a daemon running from the desktop app's bundle
- **WHEN** `GET /api/v1/daemon/upgrade` is read
- **THEN** it reports that this daemon does not check, and nothing is fetched

### Requirement: Upgrade the installed binaries from the command line
`coffer update` MUST upgrade the installer's frozen binaries to the newest
release: download the command-line archive for this machine and the release's
`SHA256SUMS`, refuse an archive whose checksum does not match, put each binary
over its public name in `~/.coffer/bin` the way the installer does (a temporary
sibling, then a rename), with the shim's `coffer-mcp-shim-lib/` folder put beside
it the same way before the shim itself, and restart the daemon from the new
`~/.coffer/bin/coffer-daemon`. Nothing is replaced until the archive has
verified. `coffer update --check` MUST only report the running and the newest
version. When the running daemon is the desktop app's, `coffer update` MUST ask
the app to install its signed update instead (`coffer app update install`); a
source run MUST say to upgrade the checkout and change nothing. Already on the
newest release it MUST say so and change nothing.

#### Scenario: an update installs the verified archive and restarts the daemon
- **GIVEN** Coffer 0.3.0 installed by the installer and a latest release v0.4.0 whose archive matches its checksum
- **WHEN** the person runs `coffer update`
- **THEN** the binaries in `~/.coffer/bin` are 0.4.0's and the daemon is restarted from them

#### Scenario: an archive that does not match its checksum installs nothing
- **GIVEN** a latest release whose archive's SHA-256 differs from its `SHA256SUMS` line
- **WHEN** the person runs `coffer update`
- **THEN** it fails naming the checksum mismatch and `~/.coffer/bin` is unchanged

### Requirement: Uninstall Coffer from this machine
`POST /api/v1/daemon/uninstall` MUST remove what Coffer wrote outside
`~/.coffer` and then stop the daemon, so uninstalling is one action instead of a
list of manual steps. In order, it MUST take the model-provider routing out of
every agent's settings, disconnect every agent (its MCP entry and memory hook),
remove every skill link Coffer delivered with its delivery records, keep any
reconcile pass from restoring them, remove the start-at-login job, remove the
terminal launch files Coffer wrote, remove the installer's `PATH` lines (the
`# Added by Coffer installer` marker and the line after it) from the shell
profiles, and delete `~/.coffer/bin`. Each step MUST be attempted even when an
earlier one failed, and the answer MUST list every step as done, nothing to do,
or failed with its reason. The vault, the settings, the skills' own folders and
the history MUST stay, so installing Coffer again finds them.

With `delete_data`, the request MUST carry a presence grant for the operation
`uninstall` over the target `delete-data`, redeemed before anything changes; an
unverified grant MUST refuse the whole request. After the daemon has stopped
serving and released its lock, it MUST then delete the master key's Keychain
items and `~/.coffer`.

`coffer uninstall` MUST run the same. With the desktop app installed it MUST
open the app's uninstall dialog instead, where the person confirms. Otherwise it
MUST ask before uninstalling, unless `--yes` is given; `--delete-data` MUST ask
for the words `delete my data` at an interactive terminal — no flag skips that,
and without a terminal it MUST refuse — and deletes `~/.coffer` only after the
daemon has exited. The command line MUST NOT touch the Keychain, which only the
daemon owns: it MUST say that the master key's Keychain items stay.

#### Scenario: uninstall removes every footprint and keeps the vault
- **GIVEN** a connected agent with a provider switch, two delivered skills, start at login on and the installer's `PATH` line in `~/.zshrc`
- **WHEN** `POST /api/v1/daemon/uninstall` is called without `delete_data`
- **THEN** the agent's MCP entry, memory hook and provider keys are gone, the skill links are gone, the launch agent is gone, the `PATH` line and its marker are gone and `~/.coffer/bin` is gone
- **AND** the answer lists each step and the daemon stops, while `~/.coffer/vault` is unchanged

#### Scenario: deleting the data needs a presence grant
- **GIVEN** a running daemon
- **WHEN** `POST /api/v1/daemon/uninstall` is called with `delete_data` and no valid grant
- **THEN** it is refused and nothing is removed

#### Scenario: the command line will not delete the data without a terminal
- **GIVEN** no desktop app installed
- **WHEN** `coffer uninstall --delete-data --yes` runs with no interactive terminal
- **THEN** it refuses, and nothing is removed

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

### Requirement: Delete what exited one-file binaries unpacked
Each of Coffer's one-file binaries (`coffer`, `coffer-daemon`, `coffer-seatalk-bridge`) MUST
write its process id into the directory its bootloader unpacked it into (`$TMPDIR/_MEI*`) before
any Coffer code runs. A frozen daemon MUST, when it starts and every 6 hours after, delete each
such directory whose marked process no longer runs. It MUST NOT delete an unmarked directory —
another PyInstaller program's, or one whose process has not marked it yet — nor its own. The
bootloader removes the directory when its program exits, but not when the process is killed
outright, and each leftover is the size of the whole archive.

#### Scenario: a frozen daemon deletes the unpack directories of exited Coffer binaries
- **GIVEN** `$TMPDIR` holding a `_MEI*` directory marked with the pid of an exited Coffer process, one marked with a running process's pid, and one with no mark
- **WHEN** a frozen daemon starts
- **THEN** the directory of the exited process is deleted
- **AND** the other two, and the daemon's own unpack directory, are left as they were
