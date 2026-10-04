## MODIFIED Requirements

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
- **GIVEN** a `daemon.log` holding Coffer's own structured JSON, a uvicorn line, a `LEVEL - logger - message` line from an upstream, a colour-escaped line from an upstream, and a multi-line traceback,
- **WHEN** `GET /api/v1/daemon/logs` is called with a token,
- **THEN** the response is newest-first and bounded by `limit`, every record carries the time, level and logger its line actually stated, escape sequences are stripped, the traceback rides with the record that raised it, and a line no format fits is kept whole rather than dropped,
- **AND** `level` and `since` narrow the window, while the same call with no token is rejected even though `/daemon/status` on the same router is open.

#### Scenario: the command line reads the daemon log tail
- **GIVEN** a running daemon whose `daemon.log` holds an info record, an error record carrying a traceback, and a record older than one hour,
- **WHEN** the user runs `coffer log daemon --json --since 1h`, then `coffer log daemon --errors --limit 1`,
- **THEN** the first prints, newest-first, the two recent records exactly as `GET /api/v1/daemon/logs` returns them for that window, the older record absent,
- **AND** the second prints only the error record, with its traceback riding with it.
