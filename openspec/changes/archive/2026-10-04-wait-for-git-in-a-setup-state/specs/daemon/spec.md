## ADDED Requirements

### Requirement: Wait in a setup state when git is missing or too old
The vault is a git repository and every sync round's merge needs git 2.40, so
git is a hard dependency. Before it opens the vault the daemon MUST look for a
git of version 2.40 or later, first on its own `PATH`, then on the `PATH` the
person's login shell reports; a git good enough only on the login shell's
`PATH` MUST be used, by putting its directory first on the daemon's `PATH`.

Without one the daemon MUST still start and serve, in a **setup state**: it
serves the web UI, publishes its token and port as every start does, and wires
nothing that touches the vault — no migrations, vault, kinds, workers or MCP
sessions. `GET /api/v1/daemon/status` MUST report `status: "setup"` and a
`setup` object: `need: "git"`, `reason` (`git_missing` when no git was found,
`git_too_old` naming the newest version found as `found`), `needed` (`2.40`),
a `message` saying what is wrong, that the vault keeps its history and syncs
with git, and what to do, and `handoff`, the prompt asking the person's agent
to install or update git — naming the machine and no installer, as the other
git hand-offs do. Every other API route and `/mcp` MUST answer 503
`GIT_NEEDED` with that message and, in `details`, the reason, the versions and
the hand-off — except the status, `POST /api/v1/daemon/setup/check`,
`/daemon/restart` and `/daemon/shutdown`.

`POST /api/v1/daemon/setup/check` MUST look for git again, both `PATH`s, never
from a cached answer, and answer `ready: true` once a usable git is there (a
login-shell git is put first on the daemon's `PATH`, so a restart's successor
inherits it), or `ready: false` with the current `setup`. A restart then starts
the daemon normally. A `coffer` command that needs the daemon MUST print the
message and the hand-off and exit 10 instead of sending its request; `coffer
daemon status` MUST report the state and the same words, and `coffer daemon
start` MUST say them once the daemon answers. The MCP shim MUST pass a
refusal's message and hand-off to the agent whole.

#### Scenario: a machine without git starts the daemon in its setup state
- **GIVEN** a machine with no `git` on the daemon's `PATH` or the login shell's
- **WHEN** the daemon starts
- **THEN** it serves, and `GET /api/v1/daemon/status` reports `status: "setup"` with `reason: "git_missing"`, `needed: "2.40"` and a prompt asking an agent to install git that names no installer
- **AND** no vault repository was created

#### Scenario: a git older than 2.40 puts the daemon in its setup state with a hand-off
- **GIVEN** a machine whose only `git` reports version 2.30
- **WHEN** the daemon starts
- **THEN** the status reports `reason: "git_too_old"`, `found: "2.30"` and `needed: "2.40"`
- **AND** its hand-off asks an agent to update git and confirm with `git --version`, and names no installer

#### Scenario: a git only on the login shell's PATH is used
- **GIVEN** a daemon whose own `PATH` has git 2.30 and a login shell whose `PATH` has git 2.45
- **WHEN** the daemon looks for git
- **THEN** it uses the login shell's git, whose directory comes first on the daemon's `PATH`

#### Scenario: the setup state refuses what needs the vault
- **GIVEN** a daemon in its setup state
- **WHEN** an API route that needs the vault, or `/mcp`, is called
- **THEN** it answers 503 `GIT_NEEDED` with the setup message, and `details` carry the reason and the hand-off
- **AND** the status, Check again, restart and shutdown routes still answer

#### Scenario: check again finds git and the restart finishes the start
- **GIVEN** a daemon in its setup state, on a machine where git 2.45 has since been installed
- **WHEN** `POST /api/v1/daemon/setup/check` is called
- **THEN** it answers `ready: true`
- **AND** with git still missing it answers `ready: false` and the current setup state

#### Scenario: a command that needs the daemon prints why it waits
- **GIVEN** a daemon in its setup state
- **WHEN** a `coffer` command that needs the daemon runs
- **THEN** it prints the setup message and the hand-off prompt and exits 10, sending no request of its own
- **AND** `coffer daemon status` prints `status: setup` with the same message and exits 0

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
entry each for `knowledge`, `memory`, `sync` and `models` (spec
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
- **THEN** the response carries a `features` map with one entry per registered experimental feature (`knowledge`, `memory`, `sync` and `models`), and this machine's `machine_id` and `machine_name`
