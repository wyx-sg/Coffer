## REMOVED Requirements

### Requirement: Stand down after an idle window
**Reason**: The owner decided the daemon never stands down on its own. A resident daemon is what the login service is for, and whatever has to answer at any hour — a channel's inbound connection first — needed a hold to survive the idle clock, so the window mostly measured which exceptions had been remembered.
**Migration**: None needed. `idle_shutdown_hours` is ignored when `~/.coffer/daemon-config.json` is read and dropped when it is next written; `coffer daemon idle` is removed; `GET`/`PUT /api/v1/daemon/residency` carry the login service only. Stop a daemon with `coffer daemon stop`.

## MODIFIED Requirements

### Requirement: Manage the daemon from the command line
Users MUST be able to run `coffer daemon start`, `stop`, `restart`, `status [--json]`,
`rotate-token`, `port show|set|clear` and `service install|uninstall|status`. `start` MUST key off the liveness probe rather than the
presence of `daemon.json`, MUST diagnose a port that is already held *before* spawning rather than
after a boot timeout, and MUST wait a bounded time for the daemon to publish itself. That pre-flight
check MUST be allowed to report "free" when the port is not — a port in `TIME_WAIT` from the daemon
a `restart` has just stopped is bindable and must not be called a conflict — and MUST never err the
other way: a missed conflict resolves downstream as "already running", while a false one blocks a
legitimate start. `stop` MUST confirm the recorded pid is still a Coffer daemon before signalling
it, and MUST clean up the stale discovery file instead when it is not. `restart` is `stop` then
`start`, and is how a setting read before the bind takes effect. The `port` and `service`
groups MUST work with no daemon running (see "Bind a fixed, settable port" and "Change residency
from the settings page or the command line").

#### Scenario: a recorded pid that is not ours is never signalled
- **GIVEN** a `~/.coffer/daemon.json` whose recorded pid has been recycled onto an unrelated process,
- **WHEN** the user runs `coffer daemon stop`,
- **THEN** no signal is sent to that process; the stale discovery file is removed instead, and the command says so.

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
- **AND** a daemon that dies badly is restarted, while one that exited cleanly on purpose is left alone.

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
- **WHEN** the daemon starts, and the user then runs `coffer daemon port set` with another port,
- **THEN** the daemon serves on the pinned port and never stands down on its own,
- **AND** the rewritten file carries the new port and no `idle_shutdown_hours` key.
