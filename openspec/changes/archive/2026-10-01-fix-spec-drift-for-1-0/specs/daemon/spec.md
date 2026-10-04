## RENAMED Requirements

- FROM: `### Requirement: Deploy frozen sibling binaries and back up the vault before migrating`
- TO: `### Requirement: Deploy frozen sibling binaries and back up the history database before migrating`

## MODIFIED Requirements

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
"Deploy frozen sibling binaries and back up the history database before migrating"), so a service pinned to a
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

### Requirement: Require a token on every management call
The daemon MUST require an authentication token on every management API call. The token is minted
locally at startup, published only in the user-only-readable `daemon.json` (see "Publish one
private discovery file"), and rotatable. `GET /api/v1/daemon/status` is the one deliberate
exemption (see "Answer the status probe without a token"). The API's schema,
`GET /api/v1/openapi.json`, MUST need the token like any other management call, and the
daemon MUST NOT serve the framework's interactive API pages (`/docs`, `/redoc`) at all.

#### Scenario: a management call without the token is refused
- **GIVEN** a daemon with an active token,
- **WHEN** any route under `/api/v1` other than `/api/v1/daemon/status` is called with no token, or with a token that is not the active one,
- **THEN** it is refused with `401` before the route does anything,
- **AND** `/api/v1/daemon/status` still answers with no token.

#### Scenario: the API schema is served only to a token holder
- **GIVEN** a daemon with an active token,
- **WHEN** `/api/v1/openapi.json` is read with no token, with a wrong one and with the active one, and `/openapi.json`, `/docs` and `/redoc` are requested,
- **THEN** the schema is refused with `401` until the active token is sent, and then answers with the management routes,
- **AND** nothing answers at `/openapi.json`, `/docs` or `/redoc`.

### Requirement: Deploy frozen sibling binaries and back up the history database before migrating
When the daemon detects that it is running as a frozen build, it MUST idempotently deploy its
sibling binaries — `coffer`, `coffer-daemon`, `coffer-mcp-shim` — into
`~/.coffer/bin/` at startup. `coffer` is in that list so that a user who installed only the desktop
tier has the management CLI on disk after the first launch, and `coffer-daemon` so the frozen shim
can resolve it as a sibling. Each build MUST land in its own `~/.coffer/bin/<version>/` directory,
with the public `~/.coffer/bin/<name>` paths being symlinks into it that are flipped atomically, so
that a deploy never overwrites a binary in place and the previous version's directory stays on disk
for a rollback (the two newest version directories are kept; older ones are pruned). The copy MUST
be atomic (temp sibling in the same directory, executable bit set, then rename, with the version
sentinel written last) so that a crash or a concurrently executing binary never observes a truncated
file, and staleness MUST be decided by two signals — byte size and the version sentinel — never
mtime, which says when a build was extracted rather than what it contains. A deploy MUST also
remove every public `~/.coffer/bin/<name>` symlink that points into a version directory under a
name this build does not ship, so a binary a release dropped stops resolving to an old build
instead of lingering on the user's `PATH`; anything at such a path that is not a symlink into a
version directory is not Coffer's deployment and MUST be left alone.

Before `alembic upgrade head` changes the on-disk history database, `~/.coffer/runs.db`, the
daemon MUST copy it (and any `-wal`/`-shm` companions) to `runs.db.pre-<revision>`, keeping the
three newest copies; an already-current schema or an in-memory database MUST NOT be copied.
Before any of that the daemon MUST refuse a home that still holds only the single database of
the layout before the vault, naming `coffer migrate`: moving a home into the vault layout is a
step of its own that backs the old database up as `coffer.db.pre-vault` first, never a startup
migration ([vault-storage](../vault-storage/spec.md) "Move an existing home into the vault layout once, on request, reversibly"). A source install MUST NOT do
any of this: `pip install` already puts the console scripts on `PATH` (see "Install the console
scripts from source"). The daemon owns the deployment because it is the one process every frozen install starts,
whichever tier it came from.

#### Scenario: a frozen daemon deploys its sibling binaries on start
- **GIVEN** a frozen `coffer-daemon` started from an extracted release archive, with `coffer` and `coffer-mcp-shim` beside it,
- **WHEN** the daemon starts,
- **THEN** each sibling binary is reachable and executable at `~/.coffer/bin/<name>` — a symlink into `~/.coffer/bin/<version>/`, where the file was copied atomically through a temp sibling and a rename, and the symlink itself was flipped atomically,
- **AND** a second start with nothing changed leaves those files untouched, while a version change deploys the new build into its own `<version>/` directory and re-points the symlinks — as decided by the byte-size and version-sentinel staleness check — keeping the previous version's directory on disk so the upgrade can be undone by pointing the links back; only the two newest version directories are kept.

#### Scenario: a deploy removes the link of a binary the build no longer ships
- **GIVEN** `~/.coffer/bin/coffer-callback` is a symlink into a version directory an earlier build deployed, and a frozen `coffer-daemon` whose build ships only `coffer`, `coffer-daemon` and `coffer-mcp-shim`,
- **WHEN** the daemon starts and deploys its siblings,
- **THEN** `~/.coffer/bin/coffer-callback` no longer exists, while `coffer`, `coffer-daemon` and `coffer-mcp-shim` point into the new build's version directory,
- **AND** a regular file at `~/.coffer/bin/<name>` for a name the build does not ship is left untouched.

#### Scenario: a schema upgrade keeps a copy of the history database
- **GIVEN** a daemon starting against a `runs.db` whose Alembic revision is behind this build's head,
- **WHEN** the migrations run at startup,
- **THEN** `runs.db.pre-<revision>` (with its `-wal`/`-shm` companions, when present) holds the pre-upgrade state beside the live file, only the three newest such copies are kept, and a start against an already-current schema — or an in-memory database — copies nothing.
