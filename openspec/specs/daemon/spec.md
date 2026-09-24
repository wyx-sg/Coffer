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
the whole of the access model, there is no multi-tenant or remote-access requirement, and the
daemon itself is never exposed through a tunnel — only the separate `coffer-callback` listener of
the channels spec is. Process inspection is available for processes the user owns; wherever it is
not, every rule here reads the answer as "not ours" and does nothing, which is the safe direction
for all of them. The desktop shell of the desktop-app spec reads `daemon.json` and drives
`POST /daemon/shutdown` from Rust, in a separate crate: the file's shape is this spec's to change,
and a change to it is a change to that shell. There is no fleet, no leader election and no
daemon-to-daemon protocol; the daemon spawns children but does not install runtimes or package
managers for them, and the `.dmg` and the shell inside it belong to the desktop-app spec, which
wraps the same four binaries this spec builds.

Not every daemon operation is reachable from both REST and the CLI. Three gaps are deliberate and
one is not. The pre-bind port setting is CLI-only by design, because it must work with no daemon
running. The `/api/v1/fs/*` routes are REST-only because their only caller is a web page that
cannot reach the OS by itself, while a terminal user already has `cd`, `$EDITOR` and their
platform's own open command. `POST /daemon/shutdown` has no dedicated CLI verb because
`coffer daemon stop` reaches the same exit through a signal. The gap with no reason behind it is
`GET /api/v1/daemon/logs`, which has no `coffer daemon logs` counterpart — a terminal user reads
the file directly, which works but is not the same contract. `COFFER_PORT_RANGE_START` /
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

#### Scenario: two racing spawns produce one daemon
- **GIVEN** no daemon is running and two surfaces (a CLI command and an MCP shim) each decide to spawn one at the same moment,
- **WHEN** both spawned processes run their detect-or-spawn sequence,
- **THEN** exactly one binds a port and publishes `~/.coffer/daemon.json`, and the other observes it is already live and exits without binding,
- **AND** the loser blocks on the spawn lock until the winner is serving HTTP, so it never probes a bound-but-not-yet-answering port and concludes nobody is there.

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
`GET /api/v1/daemon/status` MUST be unauthenticated and MUST answer during startup, before the
daemon has finished wiring itself up, because it is the readiness probe every other rule here keys
off. It MUST report the lifecycle phase (`starting`, `ready`, `draining`), the bound port, the
start time, the build's version and the executable answering. It MUST also report the build's
release channel, the on/off state of every experimental feature (spec
[experimental-features](../experimental-features/spec.md) "Decide a feature's state per machine"),
and this machine's id and name — the identity a channel is bound to, which cannot sit behind the
sync routes because those close while `vault_sync` is switched off. It MAY carry a count of registered,
enabled, healthy and unhealthy upstreams when those are available, and MUST still answer when they
are not.

#### Scenario: daemon status reflects ready state
- **GIVEN** the daemon has just been started,
- **WHEN** `GET /api/v1/daemon/status` is called,
- **THEN** the response reports `status: "ready"`, a non-zero `port`, a `started_at` timestamp, the daemon's `version` and its `executable` — and the same port and start time are written to `~/.coffer/daemon.json`,
- **AND** the call succeeds with no token, because it is the readiness probe every other lifecycle rule keys off,
- **AND** a CLI or shim whose own version differs from the reported one prints a one-line warning naming both builds and the executable, and carries on.

#### Scenario: daemon status names this machine and its features
- **GIVEN** a running daemon with `vault_sync` switched off
- **WHEN** `GET /api/v1/daemon/status` is called with no token
- **THEN** the response carries `channel`, a `features` map naming `vault_sync`, `knowledge` and `memory`, and this machine's `machine_id` and `machine_name`

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
Users MUST be able to run `coffer daemon start`, `stop`, `restart`, `status [--json]`,
`rotate-token`, `port show|set|clear`, `idle show|set|never` and
`service install|uninstall|status`. `start` MUST key off the liveness probe rather than the
presence of `daemon.json`, MUST diagnose a port that is already held *before* spawning rather than
after a boot timeout, and MUST wait a bounded time for the daemon to publish itself. That pre-flight
check MUST be allowed to report "free" when the port is not — a port in `TIME_WAIT` from the daemon
a `restart` has just stopped is bindable and must not be called a conflict — and MUST never err the
other way: a missed conflict resolves downstream as "already running", while a false one blocks a
legitimate start. `stop` MUST confirm the recorded pid is still a Coffer daemon before signalling
it, and MUST clean up the stale discovery file instead when it is not. `restart` is `stop` then
`start`, and is how a setting read before the bind takes effect. The `port`, `idle` and `service`
groups MUST work with no daemon running (see "Bind a fixed, settable port" and "Change residency
from the settings page or the command line").

#### Scenario: a recorded pid that is not ours is never signalled
- **GIVEN** a `~/.coffer/daemon.json` whose recorded pid has been recycled onto an unrelated process,
- **WHEN** the user runs `coffer daemon stop`,
- **THEN** no signal is sent to that process; the stale discovery file is removed instead, and the command says so.

### Requirement: Own and reap the daemon's long-lived children
The daemon MUST spawn, record and terminate every long-lived child it owns — the `coffer-callback`
listener, a channel tunnel, an agent app-server — through one path: recording the child's pid is
inseparable from spawning it, and termination is one `SIGTERM` → bounded wait → `SIGKILL` → bounded
wait ladder whose pid record is dropped only because the child was reaped here. Each child's record
is one file naming its pid and command line. At startup the daemon MUST sweep what a previous crash
left behind: recorded children, and sibling daemon processes **provably serving this same vault**.
"Not provably ours" MUST mean "leave it alone" — a candidate whose vault cannot be read, or a
matching executable running against another `HOME`, MUST NOT be touched, because a wrong kill costs
somebody a running daemon while a missed one costs only a port the next start reports. The daemon
owns `coffer-callback` as a *process*: spawning it, supervising it, and shipping and deploying it
(see "Release the macOS arm64 terminal archive" and "Deploy frozen sibling binaries and back up the
vault before migrating"). The ingress protocol that listener serves is the channels spec's.

#### Scenario: the daemon reaps only the children it can prove are its own
- **GIVEN** a previous daemon crashed leaving a recorded long-lived child running, and another daemon binary is running against a different vault under a throwaway `HOME`,
- **WHEN** a daemon starts and runs its startup sweep,
- **THEN** the recorded orphan is terminated, and the daemon serving the other vault is left untouched — anything not provably serving this vault is left alone.

### Requirement: Bind a fixed, settable port
The daemon's listening port MUST be **fixed by default and settable**, so a browser bookmark to
Coffer's UI keeps working across restarts. With nothing configured the daemon MUST bind exactly
`8000` and MUST NOT scan for an alternative; a drifting origin is not merely a broken bookmark,
because browser `localStorage` is keyed by origin, so the UI language, sidebar state, page size and
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

Users MUST be able to read and change the setting **from the CLI**, and it MUST work with no daemon
running, because a daemon that cannot bind its port is exactly the state the setting has to be
fixable from. It MUST NOT have a REST endpoint or a settings panel: a port that is correct by
default does not earn a place in the UI, and the escape hatch belongs where a squatted port is
diagnosed. A change takes effect at the next start, which `coffer daemon restart` applies in one
command. This setting is deliberately outside the audit obligation every kind inherits: it is
neither a resource nor a capability but process configuration read before the database opens, and
the CLI that owns it must work with no daemon running — so the audit table is unreachable on
exactly the path that matters most, and recording a change only when a daemon happens to be up
would be less honest than recording none.

#### Scenario: the daemon binds the same port every start
- **GIVEN** no port has been configured, so the daemon's default of 8000 applies,
- **WHEN** the daemon is stopped and started again — by the user, by the CLI, or auto-spawned by an MCP shim, which inherits no shell profile,
- **THEN** it binds 8000 every time and records it in `~/.coffer/daemon.json`, so a browser bookmark to Coffer's UI keeps working and nothing the browser stored against that origin is lost.

#### Scenario: a configured daemon port survives restarts
- **GIVEN** the user has moved the daemon's port with `coffer daemon port set <n>`,
- **WHEN** the daemon is stopped and started again by any of those routes,
- **THEN** it binds that same port every time and records it in `~/.coffer/daemon.json`.

#### Scenario: a port that is taken refuses to start and says what holds it
- **GIVEN** the port the daemon would bind — its 8000 default, or one the user configured — is already held by another process,
- **WHEN** the daemon starts,
- **THEN** it refuses to start rather than binding a different port, and the message names the process holding the port and the commands that resolve it — free that process, or `coffer daemon port set <other>`.

### Requirement: Run as a login service
The daemon MUST be installable as a **login service** — on macOS, a per-user launchd agent — so
that it is running before anything asks for it, and is restarted when it dies badly. Started only on
demand, the daemon is down at exactly the moments it is wanted: an agent's first `coffer__*` call of
the day, a channel message arriving while no window is open, a terminal session in a directory
nobody has opened Coffer from. Each of those clients can start one, and each then pays the seconds a
cold start takes, once per gap.

The service MUST restart the daemon **only on an unsuccessful exit**. A deliberate stand-down (see
"Stand down after an idle window") is a clean exit, and a supervisor that restarted those too would
turn the idle shutdown into a restart loop; nothing is lost by letting one stand, because every
client can start a daemon.

It MUST carry the user's own `PATH`, read from their login shell: a login service otherwise
inherits a minimal one, and the `npx` / `uvx` MCP upstreams the daemon spawns then resolve to
nothing — and the environment the install itself runs in is no better a source, since it is usually
the daemon's, which was commonly spawned by a GUI-launched editor and has exactly that minimal
`PATH`. It MUST start the build that is current rather than the one that was current when it was
installed: deployed binaries live under a per-version directory whose older entries are pruned (see
"Deploy frozen sibling binaries and back up the vault before migrating"), so a service pinned to a
versioned path stops working two upgrades later, and a supervisor that cannot execute its program
fails silently — which is the one way autostart could stop without anyone finding out. It MUST
write to the daemon log (see "Write one bounded daemon log in one format") rather than a file of
its own. Installing and removing it MUST be available from the CLI with no daemon running, and MUST
be reversible without trace; removing it MUST NOT stop a daemon that is already running. See
[Detect-or-Spawn](../../../docs/decisions/daemon-detect-or-spawn.md).

#### Scenario: the daemon is up before anything asks for it
- **GIVEN** a machine where the login service is installed and no Coffer window is open,
- **WHEN** the user logs in,
- **THEN** the daemon is started by the system, with the user's own `PATH`, logging to the daemon log,
- **AND** a daemon that dies badly is restarted, while one that stood down on purpose is left alone.

### Requirement: Stand down after an idle window
A daemon that nothing has wanted for long enough MUST stand down, by exiting cleanly. Resident is
not the same as immortal: without a ceiling, a login service means a python process, its MCP
upstreams and its channel listeners survive every weekend nobody worked. The window MUST be
configurable, MUST default to twelve hours — overnight and then some, so a working day's gap never
costs a restart — and MUST be settable to "never", which is the setting for a vault whose channels
must answer at any hour. It lives beside the port in `~/.coffer/daemon-config.json` for the same
reason and is read at start, so a change takes effect at the next one.

What counts as being wanted MUST be requests that reached the application, not traffic that
arrived: a request the loopback host guard refused is an attack, and counting it would keep the
daemon resident on the strength of one. It MUST also be measurable as *readiness* rather than only
as requests — a subsystem whose job is to be reachable MUST be able to hold the daemon in service
while it is, and the channel listener MUST do so, because the request that justifies it is the one
that arrives the next morning, after a daemon counting yesterday's traffic would already have gone.
The clock MUST be monotonic: a laptop that slept for nine hours did not go nine hours unused, and
standing down the instant the lid opens is the opposite of the intent.

#### Scenario: a daemon nothing has wanted stands down
- **GIVEN** a running daemon and a configured idle window,
- **WHEN** that window passes with nothing reaching the application,
- **THEN** the daemon exits cleanly, and the next client to want one starts it,
- **AND** the window does not pass while a subsystem whose job is to be reachable holds it open, nor because the machine was asleep.

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
exemption (see "Answer the status probe without a token").

#### Scenario: a management call without the token is refused
- **GIVEN** a daemon with an active token,
- **WHEN** any route under `/api/v1` other than `/api/v1/daemon/status` is called with no token, or with a token that is not the active one,
- **THEN** it is refused with `401` before the route does anything,
- **AND** `/api/v1/daemon/status` still answers with no token.

### Requirement: Rotate the token from REST or the command line
Rotation MUST be reachable from both `POST /api/v1/daemon/rotate-token` and
`coffer daemon rotate-token`. It MUST mint a fresh token, rewrite `daemon.json` atomically at mode
`0600` — never leaving the file at wider permissions for any window — publish the new value to the
in-process check so the accepted token and the token "Hand the browser its token in the served
page" injects cannot drift apart, and record a `token_rotated` audit entry. That audit obligation
stands on its own here rather than inheriting the framework's per-resource rule: a token is neither
a resource nor a capability, and a secret changing hands is exactly the event a local-only posture
is worth recording.

#### Scenario: rotating the daemon token invalidates the previous one
- **GIVEN** the daemon has issued an auth token,
- **WHEN** the user invokes the rotate-token operation, through either `POST /api/v1/daemon/rotate-token` or `coffer daemon rotate-token`,
- **THEN** subsequent management API calls with the previous token are rejected with 401, calls with the new token succeed, the new value reaches `~/.coffer/daemon.json` without the file ever existing at wider than user-only permissions, and the rotation is recorded as a `token_rotated` audit entry.

### Requirement: Refuse a request whose Host is not loopback
The daemon MUST refuse any request whose `Host` header does not name a loopback authority —
`127.0.0.1`, `localhost` or `::1`, with or without a port — answering `421` with error code
`HOST_NOT_LOOPBACK` instead of serving it. This is what makes "Hand the browser its token in the
served page" safe: binding to loopback (see "Bind every endpoint to loopback only") stops a remote
host, but not a **browser** on a page whose hostname an attacker re-resolves to `127.0.0.1` — DNS
rebinding, which the browser then treats as same-origin, so CORS does not apply. Rebinding does not
change the `Host` header, so a rebound request still names the attacker's own hostname and is
refused before it can read a token out of the served document. The rule MUST hold for every surface
the daemon exposes. It does not reach the separate `coffer-callback` listener, which is a different
process on a different port and is the only thing a tunnel is ever pointed at (the channels spec).

#### Scenario: a rebound page is refused before it can read the token
- **GIVEN** a page on an attacker-controlled origin whose hostname resolves to `127.0.0.1`, which the browser therefore treats as same-origin with the daemon,
- **WHEN** it fetches any daemon URL, including `/`,
- **THEN** the daemon refuses the request with `421 HOST_NOT_LOOPBACK` because the `Host` header still names the attacker's hostname — while the same request addressed to `127.0.0.1`, `localhost` or `::1` is served normally.

### Requirement: Serve the built web UI from the daemon's own origin
The daemon MUST serve the built web UI itself, as static files, at its own loopback origin, so the
UI is same-origin with the management API. Cross-origin access MUST therefore be off by default for
every web origin; the desktop shell's own origins (`tauri://localhost`, `http://tauri.localhost`) are
the one standing exception, since the shell loads the same UI from them and the bearer token, not the
origin, is the boundary ([desktop-app](../desktop-app/spec.md)). The Vite dev-server origins stay reachable only behind the existing `COFFER_DEV_CORS` opt-in. An
install with no built UI — the normal state of a source checkout before `npm run build` — MUST skip
the mount and keep serving the API. See
[The Daemon Serves Its Token in the Page](../../../docs/decisions/daemon-serves-the-token-in-the-page.md).

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
token on every management call"; the response body is subject to none of that. `coffer open` MUST
therefore carry no credential of its own: it reads the daemon's real port from `daemon.json` and
opens the browser at that origin.

#### Scenario: a page served by the daemon is authenticated by the daemon
- **GIVEN** a daemon that has restarted since the browser last loaded the UI, and therefore minted a new token,
- **WHEN** the browser opens any page the daemon serves — the bare `/`, a client-side route such as `/agents`, a bookmark, or a plain reload — whether it got there through `coffer open` or by typing the address,
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
reads nothing but app presence, and is guarded by the same loopback + token auth. Its two consumers
are [agent-registry](../agent-registry/spec.md) "Open config files in an external editor or reveal them" and the web-ui spec's preferred-editor setting.

#### Scenario: a path that is not absolute is refused before anything is launched
- **GIVEN** a relative path, and an absolute path that does not exist,
- **WHEN** either is sent to `POST /api/v1/fs/open` or `POST /api/v1/fs/reveal`,
- **THEN** the request is rejected with `FS_PATH_NOT_OPENABLE` (400), no launcher process is started and nothing is created,
- **AND** `GET /api/v1/fs/editors` lists the GUI editors detected on this host, each with the launcher value that `/fs/open`'s `with` field accepts.

### Requirement: Write one bounded daemon log in one format
`~/.coffer/logs/daemon.log` MUST be the one file the daemon, the children it spawns, and every
surface writing on their behalf append to — one timeline rather than one file per writer, because
the question it answers is always "what else happened around then". The directory MUST be
relocatable through `COFFER_LOG_DIR` so a packaged or test install can put it elsewhere. The file
MUST be bounded by rotation rather than by deletion, and the retention sweep that ages out the
per-process and per-upstream log files MUST NOT delete it or its rotations: it is held open, and
deleting it would leave the daemon logging nowhere until the next restart.

Because several writers share it — Coffer's own structured JSON, uvicorn, a rich-rendered upstream,
a child's zerolog, some of it colour-escaped — the file is deliberately not one format, and every
reader of it is obliged to normalise rather than to assume (see "Serve the daemon log tail
normalised"). What the daemon *itself* writes, however, MUST be one format: every record produced
inside the daemon process — its own modules and the libraries logging alongside them, alembic and
asyncio included — MUST arrive as a single line carrying, at least, the instant the record was
created, its level, the logger that emitted it and the message, with a traceback kept inside the
record that raised it rather than spread across lines that state none of those. A library MUST NOT
be able to change that by configuring logging for its own purposes: the daemon owns its root logger
for its whole life, and any library configuration that would replace it is removed at the call site
rather than tolerated and parsed around. Each record MUST appear in the file exactly once — the file
is also the redirect target for the daemon's own stdout and stderr (see "Spawn a detached daemon
from any surface that needs one"), so a process writing to both that file and its stderr would
record everything twice and make one event read as two.

#### Scenario: every line the daemon writes carries the same fields
- **GIVEN** a configured daemon, and a record emitted on an ordinary logger — one of Coffer's own modules, or a library's such as `alembic.runtime.migration` — after a migration has already run,
- **WHEN** `daemon.log` is read back,
- **THEN** that record is one line stating the instant it was created, its level, its logger and its message, and a record logged with an exception carries the traceback inside that same line rather than as lines stating none of those,
- **AND** the record appears exactly once, even though the detached daemon's own stderr is that same file.

### Requirement: Serve the daemon log tail normalised
`GET /api/v1/daemon/logs` MUST return the tail of that file, newest-first, guarded by the token even
though `/daemon/status` on the same router is not: a readiness probe is public, log contents are
not. It MUST accept `since`, a severity floor (`level`), the older `errors_only` boolean, and a
bounded `limit`, and MUST read from the tail rather than the head so a large file is never pulled
into memory whole. Every record MUST carry the timestamp, level and logger its line actually
stated, whichever writer produced it; escape sequences MUST be stripped; continuation lines such as
a traceback MUST ride with the record that raised them; and a line no format fits MUST be kept whole
rather than dropped, because it is often the interesting one.

#### Scenario: the daemon log tail reads every writer's format
- **GIVEN** a `daemon.log` holding Coffer's own structured JSON, a line in the format the daemon wrote before "Write one bounded daemon log in one format" was met, a uvicorn line, a colour-escaped line from an upstream, and a multi-line traceback,
- **WHEN** `GET /api/v1/daemon/logs` is called with a token,
- **THEN** the response is newest-first and bounded by `limit`, every record carries the time, level and logger its line actually stated, escape sequences are stripped, the traceback rides with the record that raised it, and a line no format fits is kept whole rather than dropped,
- **AND** `level` and `since` narrow the window, while the same call with no token is rejected even though `/daemon/status` on the same router is open.

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
only**: a `coffer-cli-<triple>.tar.gz` archive containing `coffer` (the management CLI),
`coffer-daemon`, `coffer-mcp-shim`, and the runtime helper binary the daemon spawns
(`coffer-callback`). The binaries MUST stay co-located inside the archive so the frozen resolution
of "Spawn a detached daemon from any surface that needs one" finds `coffer-daemon` next to
`coffer`. macOS x64 (Intel), Linux and Windows are deliberately not built — those legs were never
validated end to end. This archive carries the "no system Python required" promise on its own: on a
machine with no system Python, extracting it and running `coffer daemon start` reaches
`status: ready`, and `coffer open` renders the UI authenticated. Both tiers ship per tag: this
archive is the terminal install, and the `.dmg` of [desktop-app](../desktop-app/spec.md) "Ship the desktop tier as a macOS arm64 dmg" is the double-click one;
neither is a substitute for the other.

#### Scenario: release tag produces the CLI archive and SHA256SUMS
- **GIVEN** a release tag matching `v*` is pushed,
- **WHEN** the release workflow finishes,
- **THEN** the release contains the terminal tier — `coffer-cli-<triple>.tar.gz` for macOS arm64, holding `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-callback`, co-located,
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

### Requirement: Deploy frozen sibling binaries and back up the vault before migrating
When the daemon detects that it is running as a frozen build, it MUST idempotently deploy its
sibling binaries — `coffer`, `coffer-daemon`, `coffer-mcp-shim`, `coffer-callback` — into
`~/.coffer/bin/` at startup. `coffer` is in that list so that a user who installed only the desktop
tier has the management CLI on disk after the first launch, and `coffer-daemon` so the frozen shim
can resolve it as a sibling. Each build MUST land in its own `~/.coffer/bin/<version>/` directory,
with the public `~/.coffer/bin/<name>` paths being symlinks into it that are flipped atomically, so
that a deploy never overwrites a binary in place and the previous version's directory stays on disk
for a rollback (the two newest version directories are kept; older ones are pruned). The copy MUST
be atomic (temp sibling in the same directory, executable bit set, then rename, with the version
sentinel written last) so that a crash or a concurrently executing binary never observes a truncated
file, and staleness MUST be decided by two signals — byte size and the version sentinel — never
mtime, which says when a build was extracted rather than what it contains.

Before `alembic upgrade head` changes an on-disk `coffer.db`, the daemon MUST copy it (and any
`-wal`/`-shm` companions) to `coffer.db.pre-<revision>`, keeping the three newest copies; an
already-current schema or an in-memory database MUST NOT be copied. A source install MUST NOT do
any of this: `pip install` already puts the console scripts on `PATH` (see "Install the console
scripts from source"). The daemon owns the deployment because it is the process that spawns
`coffer-callback` at runtime.

#### Scenario: a frozen daemon deploys its sibling binaries on start
- **GIVEN** a frozen `coffer-daemon` started from an extracted release archive, with `coffer`, `coffer-mcp-shim` and `coffer-callback` beside it,
- **WHEN** the daemon starts,
- **THEN** each sibling binary is reachable and executable at `~/.coffer/bin/<name>` — a symlink into `~/.coffer/bin/<version>/`, where the file was copied atomically through a temp sibling and a rename, and the symlink itself was flipped atomically,
- **AND** a second start with nothing changed leaves those files untouched, while a version change deploys the new build into its own `<version>/` directory and re-points the symlinks — as decided by the byte-size and version-sentinel staleness check — keeping the previous version's directory on disk so the upgrade can be undone by pointing the links back; only the two newest version directories are kept.

#### Scenario: a schema upgrade keeps a copy of the vault
- **GIVEN** a daemon starting against a `coffer.db` whose Alembic revision is behind this build's head,
- **WHEN** the migrations run at startup,
- **THEN** `coffer.db.pre-<revision>` (with its `-wal`/`-shm` companions, when present) holds the pre-upgrade state beside the live file, only the three newest such copies are kept, and a start against an already-current schema — or an in-memory database — copies nothing.

### Requirement: Change residency from the settings page or the command line
The two residency settings — whether the login service is installed (see "Run as a login
service") and how long the daemon serves nothing before standing down (see "Stand down after an
idle window") — MUST be readable and settable both over REST and from the CLI.

`GET /api/v1/daemon/residency` MUST report whether a login service is supported on this host,
whether it is installed, and the idle window in hours, where `null` means never. `PUT` on the same
route MUST set both halves in one request. `idle_shutdown_hours` MUST be required on the `PUT`, and
`null` MUST mean "never stand down": because `null` already carries that meaning, an omitted field
cannot also mean "leave it alone", so the request is refused instead. A window below a quarter of
an hour MUST be refused with `422` and nothing written. The login service MUST take effect at once,
because the system's service manager is a different process; the idle window MUST take effect at
the next daemon start, because the running daemon read it when it booted. The step that can fail —
installing or removing the service — MUST run first, so a failure leaves the idle window unchanged.
On a host with no login service, a request to install one MUST leave it off and say so rather than
fail. The response MUST report what is true after the change, and the change MUST be audited as
`daemon_residency_updated` with those same values.

This pair has a REST surface where the port deliberately does not: a port is changed when the
daemon cannot start, so a route the daemon would have to serve is useless exactly then, while
residency is a settings question asked of a daemon that is working.

`coffer daemon idle show|set <hours>|never` and `coffer daemon service install|uninstall|status`
MUST read and write the same settings directly, with no daemon involved and none required, since
the state they are most often reached from is "no daemon is running". `idle set` MUST refuse a
window below the floor and write nothing; `idle set` and `idle never` MUST say that the change takes
effect at the next start. On a host that has no login service, `service install` and
`service uninstall` MUST refuse with a clear message and a non-zero exit, while `service status`
MUST exit successfully and report that a login service is not supported there. The CLI path records no audit entry, for the reason the port records none: it must
work with no daemon running, so the audit table is unreachable on exactly the path it serves.

#### Scenario: the settings page changes residency in one request
- **GIVEN** a running daemon on a host that supports a login service, with nothing configured,
- **WHEN** a client reads `GET /api/v1/daemon/residency` and then sends `PUT /api/v1/daemon/residency` with `login_service_installed: true` and `idle_shutdown_hours: 6`,
- **THEN** the read reports the default window of `12` hours, the login service is installed at once, and `6` is written to `~/.coffer/daemon-config.json` for the next start to read,
- **AND** the response and a `daemon_residency_updated` audit entry both report `login_service_installed: true` and `idle_shutdown_hours: 6`, while a `PUT` that omits `idle_shutdown_hours` is refused with `422`.

#### Scenario: the command line changes residency with no daemon running
- **GIVEN** no daemon running, on a host that supports a login service,
- **WHEN** the user runs `coffer daemon idle set 3`, `coffer daemon idle never`, `coffer daemon service install`, `coffer daemon service status` and `coffer daemon service uninstall`,
- **THEN** the idle window in `~/.coffer/daemon-config.json` becomes `3` and then `null`, each change saying it takes effect at the next start, and the login service is installed, reported installed, and removed,
- **AND** `coffer daemon idle set 0.1` is refused and writes nothing, and no database is opened and no audit entry recorded.
