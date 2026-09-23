## MODIFIED Requirements

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
