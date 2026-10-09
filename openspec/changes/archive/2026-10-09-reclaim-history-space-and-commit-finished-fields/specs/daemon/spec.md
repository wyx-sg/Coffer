## MODIFIED Requirements

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
daemon MUST write a copy of it to `runs.db.pre-<revision>` with `VACUUM INTO`: one self-contained
file holding a consistent snapshot of its live data, including what its write-ahead log still
holds, without its free pages and without `-wal`/`-shm` companions. It keeps the three newest
copies, never overwrites an earlier copy, removes a copy that failed half-way and does not migrate
without one; an already-current schema or an in-memory database MUST NOT be copied.
A source install MUST NOT do
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
- **THEN** `runs.db.pre-<revision>` holds the pre-upgrade state beside the live file as one file, with what the write-ahead log held and none of the free pages, only the three newest such copies are kept, and a start against an already-current schema — or an in-memory database — copies nothing.

