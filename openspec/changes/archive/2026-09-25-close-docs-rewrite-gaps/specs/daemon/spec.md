## MODIFIED Requirements

### Requirement: Answer the status probe without a token
`GET /api/v1/daemon/status` MUST be unauthenticated and MUST answer as soon as the daemon is
serving, because it is the readiness probe every other rule here keys off. The port only opens once
the daemon has finished wiring itself up — the server accepts connections after its startup hook
returns — so no request can be answered before then, and a client that has just spawned the daemon
MUST wait a bounded time for the probe to answer rather than read a refused connection as a
failure. It MUST report the lifecycle phase (`ready`, or `draining` once shutdown has begun), the
bound port, the start time, the build's version and the executable answering. It MUST also report
the build's release channel, the on/off state of every experimental feature (spec
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
`start`, and is how a setting read before the bind takes effect. `status` MUST only look: with no
daemon answering — no `daemon.json`, or one whose port nothing answers on — it MUST report the
daemon as not running (`{"status": "stopped"}` under `--json`) and exit non-zero, and MUST NOT
start one. The `port` and `service`
groups MUST work with no daemon running (see "Bind a fixed, settable port" and "Change residency
from the settings page or the command line").

#### Scenario: a recorded pid that is not ours is never signalled
- **GIVEN** a `~/.coffer/daemon.json` whose recorded pid has been recycled onto an unrelated process,
- **WHEN** the user runs `coffer daemon stop`,
- **THEN** no signal is sent to that process; the stale discovery file is removed instead, and the command says so.

#### Scenario: status reports a stopped daemon without starting one
- **GIVEN** no daemon is running,
- **WHEN** the user runs `coffer daemon status`, or `coffer daemon status --json`,
- **THEN** it reports the daemon as not running (`{"status": "stopped"}` under `--json`) and exits non-zero,
- **AND** no daemon is spawned and no `daemon.json` is written.
