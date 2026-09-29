## MODIFIED Requirements

### Requirement: Manage the daemon from the command line
Users MUST be able to run `coffer daemon start`, `stop`, `restart`, `status [--json]`,
`rotate-token` and `service install|uninstall|status`. `start` MUST key off the liveness probe rather than the
presence of `daemon.json`, MUST diagnose a port that is already held *before* spawning rather than
after a boot timeout, and MUST wait a bounded time for the daemon to publish itself. That pre-flight
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
read and changed with `coffer config get|set|unset daemon.port`, and it and the `service` group MUST
work with no daemon running (see "Bind a fixed, settable port" and "Change residency from the
settings page or the command line").

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

Users MUST be able to read and change the setting **from the CLI** as the key `daemon.port` of the
generic `coffer config` command ([resource-framework](../resource-framework/spec.md): one key
registry, typed validation, `unset` returns a key to its default) — `coffer config get daemon.port`
prints the configured port or the 8000 default, `coffer config set daemon.port <n>` pins one, and
`coffer config unset daemon.port` returns to 8000. Those three MUST read and write the pre-bind file
directly and MUST work with no daemon running, because a daemon that cannot bind its port is exactly
the state the setting has to be fixable from. It MUST NOT have a REST endpoint or a settings panel: a
port that is correct by default does not earn a place in the UI, and the escape hatch belongs where a
squatted port is diagnosed; `daemon.port` is therefore the one `coffer config` key no route stores. A
change takes effect at the next start, which `coffer daemon restart` applies in one
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
- **GIVEN** the user has moved the daemon's port with `coffer config set daemon.port <n>`,
- **WHEN** the daemon is stopped and started again by any of those routes,
- **THEN** it binds that same port every time and records it in `~/.coffer/daemon.json`.

#### Scenario: a port that is taken refuses to start and says what holds it
- **GIVEN** the port the daemon would bind — its 8000 default, or one the user configured — is already held by another process,
- **WHEN** the daemon starts,
- **THEN** it refuses to start rather than binding a different port, and the message names the process holding the port and the commands that resolve it — free that process, or `coffer config set daemon.port <other>`.

#### Scenario: the port key is read and changed with no daemon running
- **GIVEN** no daemon is running and no port has been configured,
- **WHEN** the user runs `coffer config get daemon.port`, then `coffer config set daemon.port 8123`, then `coffer config get daemon.port`, then `coffer config unset daemon.port`,
- **THEN** the first prints the 8000 default, the set writes 8123 into `~/.coffer/daemon-config.json`, the second get prints 8123, and the unset leaves the file carrying no port so the default applies again,
- **AND** no daemon is spawned, no database is opened and no audit entry is recorded.

### Requirement: Change residency from the settings page or the command line
The one residency setting — whether the login service is installed (see "Run as a login service")
— MUST be readable and settable both over REST and from the CLI. The daemon never stands down on
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
residency is a settings question asked of a daemon that is working.

`coffer daemon service install|uninstall|status` MUST read and write the same setting directly,
with no daemon involved and none required, since the state it is most often reached from is "no
daemon is running". On a host that has no login service, `service install` and `service uninstall`
MUST refuse with a clear message and a non-zero exit, while `service status` MUST exit successfully
and report that a login service is not supported there. The CLI path records no audit entry, for
the reason the port records none: it must work with no daemon running, so the audit table is
unreachable on exactly the path it serves.

`~/.coffer/daemon-config.json` MUST NOT carry an idle window. An `idle_shutdown_hours` key an earlier
build wrote there MUST be ignored when the file is read and MUST be dropped the next time the file
is written, so the file only ever states settings that still decide something.

#### Scenario: the settings page changes residency in one request
- **GIVEN** a running daemon on a host that supports a login service, with nothing configured,
- **WHEN** a client reads `GET /api/v1/daemon/residency` and then sends `PUT /api/v1/daemon/residency` with `login_service_installed: true`,
- **THEN** the read reports a supported login service that is not installed, and the login service is installed at once,
- **AND** the response and a `daemon_residency_updated` audit entry both report `login_service_installed: true`, and neither carries an idle window.

#### Scenario: the command line changes residency with no daemon running
- **GIVEN** no daemon running, on a host that supports a login service,
- **WHEN** the user runs `coffer daemon service install`, `coffer daemon service status` and `coffer daemon service uninstall`,
- **THEN** the login service is installed, reported installed, and removed,
- **AND** no database is opened and no audit entry recorded, and `coffer daemon idle` is not a command.

#### Scenario: an idle window left in the daemon config is ignored and dropped
- **GIVEN** a `~/.coffer/daemon-config.json` an earlier build wrote, carrying `idle_shutdown_hours: 6` beside a pinned port,
- **WHEN** the daemon starts, and the user then runs `coffer config set daemon.port` with another port,
- **THEN** the daemon serves on the pinned port and never stands down on its own,
- **AND** the rewritten file carries the new port and no `idle_shutdown_hours` key.

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

Because several writers share it — Coffer's own structured JSON, uvicorn, a rich-rendered upstream,
some of it colour-escaped — the file is deliberately not one format, and every
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
rather than dropped, because it is often the interesting one.

`coffer log daemon [--since <when>] [--errors] [--limit <n>] [--json]` MUST read the same tail
through that route — the one the Activity page reads — so a terminal sees the same normalised
records the page shows: `--since` and `--limit` pass through, `--errors` narrows to errors, the
table form prints one record per entry with its time, level, logger and message, and `--json`
prints the records as the route returns them. A refusal from the route MUST be printed with the
route's error and a non-zero exit.

#### Scenario: the daemon log tail reads every writer's format
- **GIVEN** a `daemon.log` holding Coffer's own structured JSON, a line in the format the daemon wrote before "Write one bounded daemon log in one format" was met, a uvicorn line, a colour-escaped line from an upstream, and a multi-line traceback,
- **WHEN** `GET /api/v1/daemon/logs` is called with a token,
- **THEN** the response is newest-first and bounded by `limit`, every record carries the time, level and logger its line actually stated, escape sequences are stripped, the traceback rides with the record that raised it, and a line no format fits is kept whole rather than dropped,
- **AND** `level` and `since` narrow the window, while the same call with no token is rejected even though `/daemon/status` on the same router is open.

#### Scenario: the command line reads the daemon log tail
- **GIVEN** a running daemon whose `daemon.log` holds an info record, an error record carrying a traceback, and a record older than one hour,
- **WHEN** the user runs `coffer log daemon --json --since 1h`, then `coffer log daemon --errors --limit 1`,
- **THEN** the first prints, newest-first, the two recent records exactly as `GET /api/v1/daemon/logs` returns them for that window, the older record absent,
- **AND** the second prints only the error record, with its traceback riding with it.
