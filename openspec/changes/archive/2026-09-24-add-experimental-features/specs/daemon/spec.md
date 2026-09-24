## MODIFIED Requirements

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
