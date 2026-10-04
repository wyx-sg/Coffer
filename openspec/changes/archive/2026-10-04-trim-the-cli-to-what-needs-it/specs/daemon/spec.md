## MODIFIED Requirements

### Requirement: Manage the daemon from the command line
Users MUST be able to run `coffer daemon start`, `stop`, `restart` and `status [--json]`, with the daemon down or wedged. `start` MUST key off the liveness probe rather than the
presence of `daemon.json`, MUST diagnose a port that is already held *before* spawning rather than
after a boot timeout, and MUST wait a bounded time for the spawned daemon to **answer its status call** — a published
`daemon.json` is not that, because the file is written before the daemon has finished starting and a
stale one left by a crash is there before it has started at all. A daemon that exits before it
answers (a vault migration is required, git is too old) MUST be reported as failed with a pointer to
`daemon.log`, never as started. That pre-flight
check MUST be allowed to report "free" when the port is not — a port in `TIME_WAIT` from the daemon
a `restart` has just stopped is bindable and must not be called a conflict — and MUST never err the
other way: a missed conflict resolves downstream as "already running", while a false one blocks a
legitimate start. `stop` MUST confirm the recorded pid is still a Coffer daemon before signalling
it, and MUST clean up the stale discovery file instead when it is not. `restart` is `stop` then
`start`, and is how a setting read before the bind takes effect. `status` MUST only look: with no
daemon answering — no `daemon.json`, or one whose port nothing answers on — it MUST report the
daemon as not running (`{"status": "stopped"}` under `--json`) and exit non-zero, and MUST NOT
start one. With a daemon answering, `status` MUST also report the passes in flight — the list
[resource-framework](../resource-framework/spec.md) "Report the passes in flight in one cross-kind read"
defines, each with its kind, its target and when it started — in its own section of the table form,
which says so when nothing is running, and as part of the object under `--json`. The daemon port is
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

### Requirement: Rotate the token from REST or the command line
Rotation MUST be reachable through `POST /api/v1/daemon/rotate-token`, and no command rotates the token. It MUST mint a fresh token, rewrite `daemon.json` atomically at mode
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

### Requirement: Release the macOS arm64 terminal archive
The release pipeline MUST produce, per `v*` tag, the **terminal-install tier** for **macOS arm64
only**: a `coffer-cli-<triple>.tar.gz` archive containing exactly three binaries: `coffer` (the
management CLI), `coffer-daemon` and `coffer-mcp-shim`. The binaries MUST stay co-located inside the archive so the frozen resolution
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
- **THEN** the release contains the terminal tier — `coffer-cli-<triple>.tar.gz` for macOS arm64, holding `coffer`, `coffer-daemon` and `coffer-mcp-shim`, co-located, and no other binary,
- **AND** the release contains a single aggregated `SHA256SUMS` file covering every artifact of every tier, including the desktop tier of [desktop-app](../desktop-app/spec.md) "Ship the desktop tier as a macOS arm64 dmg",
- **AND** no other platform is built.

### Requirement: Change residency from the settings page or the command line
The one residency setting — whether the login service is installed (see "Run as a login service")
— MUST be readable and settable over REST, from Settings → Daemon. The daemon never stands down on
its own: once started it serves until it is stopped, or until another daemon supersedes it (see
"Stand down only when provably superseded"), so there is no idle window to configure.

`GET /api/v1/daemon/residency` MUST report whether a login service is supported on this host and
whether it is installed. `PUT` on the same route MUST install or remove it, and the change MUST take
effect at once, because the system's service manager is a different process. On a host with no
login service, a request to install one MUST leave it off and say so rather than fail. The response
MUST report what is true after the change, and the change MUST be audited as
`daemon_residency_updated` with that same value.

This setting has a REST surface where the port deliberately does not: a port is changed when the
daemon cannot start, so a route the daemon would have to serve is useless exactly then, while
residency is a settings question asked of a daemon that is working, so it has no command.

There MUST be no command line for it: `coffer daemon service` and `coffer daemon idle` are not
commands, and the login service is installed and removed only through the route above.

#### Scenario: the settings page changes residency in one request
- **GIVEN** a running daemon on a host that supports a login service, with nothing configured,
- **WHEN** a client reads `GET /api/v1/daemon/residency` and then sends `PUT /api/v1/daemon/residency` with `login_service_installed: true`,
- **THEN** the read reports a supported login service that is not installed, and the login service is installed at once,
- **AND** the response and a `daemon_residency_updated` audit entry both report `login_service_installed: true`, and neither carries an idle window.

#### Scenario: the command line changes residency with no daemon running
- **GIVEN** no daemon running, on a host that supports a login service,
- **WHEN** the user runs `coffer daemon service install`, then `coffer daemon service status`,
- **THEN** each exits non-zero as an unknown command and the login service is neither installed nor removed,
- **AND** no database is opened and no audit entry recorded, and `coffer daemon idle` is not a command either.

### Requirement: Supervise the model proxy from the daemon
The daemon MUST supervise the local model proxy as its one sibling process, started from the
daemon's own binary in proxy mode (`coffer-daemon proxy`): at start it re-attaches to a running
proxy of the same version found through `~/.coffer/proxy.json` (`port`, `pid`, `started_at`,
`version` and a control token, mode `0600`), asks a proxy of another version to drain and replaces
it once it exits, and spawns one when none is running; it health-checks the proxy on a short period
and restarts it after a crash. It pushes the proxy what it serves — the agents' token digests and
each agent's route with the decrypted keys, held only in the proxy's memory — over the proxy's
authenticated loopback control route after every reconcile pass and whenever a token changes. The
daemon stopping or restarting MUST NOT stop the proxy, so agents' in-flight model streams outlive a
daemon upgrade. `GET /api/v1/proxy/status` reports whether it runs, its
port, pid, version, restart count and last error.

#### Scenario: the daemon restarts a crashed proxy
- **GIVEN** a supervised proxy
- **WHEN** the proxy process is killed
- **THEN** the supervisor spawns a new one on the same port, pushes it the current state, and counts the restart

#### Scenario: a daemon restart re-attaches to the running proxy
- **GIVEN** a proxy started by an earlier supervisor that has since stopped
- **WHEN** a new supervisor starts
- **THEN** it attaches to the same proxy process rather than spawning another
