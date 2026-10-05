## REMOVED Requirements

### Requirement: Change residency from the settings page
**Reason**: The owner decided (2026-10-05) that every management operation a person can do in the web UI or the desktop app has a `coffer` command, so an agent can do it too; the rule that a web UI operation owes no command is withdrawn.
**Migration**: Nothing to migrate: `coffer daemon residency show|set` call the existing route.

## ADDED Requirements

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

## RENAMED Requirements

- FROM: `### Requirement: Rotate the token over REST`
- TO: `### Requirement: Rotate the token over REST and on the command line`

## MODIFIED Requirements

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

