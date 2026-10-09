## MODIFIED Requirements

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
