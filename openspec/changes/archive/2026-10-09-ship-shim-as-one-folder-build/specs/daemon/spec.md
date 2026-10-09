## MODIFIED Requirements

### Requirement: Release the macOS arm64 terminal archive
The release pipeline MUST produce, per `v*` tag, the **terminal-install tier** for **macOS arm64
only**: a `coffer-cli-<triple>.tar.gz` archive containing exactly four binaries: `coffer` (the
management CLI), `coffer-daemon`, `coffer-mcp-shim` and `coffer-seatalk-bridge` (the executable
that loads the SeaTalk SDK on the daemon's behalf, see [channels/seatalk](../channels/seatalk/spec.md)
"Load the websocket client library from an operator-supplied directory"), plus `coffer-mcp-shim-lib/`,
the folder of libraries the one-folder shim loads from beside itself (see
[ADR distribution-pyinstaller](../../../docs/decisions/distribution-pyinstaller.md)). The binaries MUST stay co-located inside the archive so the frozen resolution
of "Spawn a detached daemon from any surface that needs one" finds `coffer-daemon` next to
`coffer`. macOS x64 (Intel), Linux and Windows are deliberately not built — those legs were never
validated end to end. This archive carries the "no system Python required" promise on its own: on a
machine with no system Python, extracting it and running `coffer daemon start` reaches
`status: ready`, and the daemon serves the UI, which renders authenticated at the origin `daemon.json` names. Both tiers ship per tag: this
archive is the terminal install, and the `.dmg` of [desktop-app](../desktop-app/spec.md) "Ship the desktop tier as a macOS arm64 dmg" is the double-click one;
neither is a substitute for the other.

#### Scenario: release tag produces the CLI archive and SHA256SUMS
- **GIVEN** a release tag matching `v*` is pushed,
- **WHEN** the release workflow finishes,
- **THEN** the release contains the terminal tier — `coffer-cli-<triple>.tar.gz` for macOS arm64, holding `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-seatalk-bridge`, co-located with the shim's `coffer-mcp-shim-lib/` folder, and no other binary,
- **AND** the release contains a single aggregated `SHA256SUMS` file covering every artifact of every tier, including the desktop tier of [desktop-app](../desktop-app/spec.md) "Ship the desktop tier as a macOS arm64 dmg",
- **AND** no other platform is built.

### Requirement: Deploy frozen sibling binaries and back up the history database before migrating
When the daemon detects that it is running as a frozen build, it MUST idempotently deploy its
sibling binaries — `coffer`, `coffer-daemon`, `coffer-mcp-shim` — into
`~/.coffer/bin/` at startup. `coffer` is in that list so that a user who installed only the desktop
tier has the management CLI on disk after the first launch, and `coffer-daemon` so the frozen shim
can resolve it as a sibling. The shim is a one-folder build: its library folder,
`coffer-mcp-shim-lib/`, MUST be deployed with it into the same version directory, before the
executable, and a version directory whose shim lacks that folder MUST be deployed again. The
daemon finds each sibling beside itself or, in the desktop app, in `Contents/Resources`, where the
app keeps the shim. Each build MUST land in its own `~/.coffer/bin/<version>/` directory,
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
- **THEN** `runs.db.pre-<revision>` (with its `-wal`/`-shm` companions, when present) holds the pre-upgrade state beside the live file, only the three newest such copies are kept, and a start against an already-current schema — or an in-memory database — copies nothing.

#### Scenario: the shim's library folder is deployed with it
- **GIVEN** a frozen `coffer-daemon` whose build holds `coffer-mcp-shim` with its `coffer-mcp-shim-lib/` folder, beside the daemon or in the app's `Contents/Resources`
- **WHEN** the daemon starts
- **THEN** `~/.coffer/bin/<version>/` holds the shim with `coffer-mcp-shim-lib/` beside it, and `~/.coffer/bin/coffer-mcp-shim` starts from there
- **AND** a later start finding that version's folder missing deploys the shim again

### Requirement: Upgrade the installed binaries from the command line
`coffer update` MUST upgrade the installer's frozen binaries to the newest
release: download the command-line archive for this machine and the release's
`SHA256SUMS`, refuse an archive whose checksum does not match, put each binary
over its public name in `~/.coffer/bin` the way the installer does (a temporary
sibling, then a rename), with the shim's `coffer-mcp-shim-lib/` folder put beside
it the same way before the shim itself, and restart the daemon from the new
`~/.coffer/bin/coffer-daemon`. Nothing is replaced until the archive has
verified. `coffer update --check` MUST only report the running and the newest
version. When the running daemon is the desktop app's, `coffer update` MUST ask
the app to install its signed update instead (`coffer app update install`); a
source run MUST say to upgrade the checkout and change nothing. Already on the
newest release it MUST say so and change nothing.

#### Scenario: an update installs the verified archive and restarts the daemon
- **GIVEN** Coffer 0.3.0 installed by the installer and a latest release v0.4.0 whose archive matches its checksum
- **WHEN** the person runs `coffer update`
- **THEN** the binaries in `~/.coffer/bin` are 0.4.0's and the daemon is restarted from them

#### Scenario: an archive that does not match its checksum installs nothing
- **GIVEN** a latest release whose archive's SHA-256 differs from its `SHA256SUMS` line
- **WHEN** the person runs `coffer update`
- **THEN** it fails naming the checksum mismatch and `~/.coffer/bin` is unchanged

## ADDED Requirements

### Requirement: Delete what exited one-file binaries unpacked
Each of Coffer's one-file binaries (`coffer`, `coffer-daemon`, `coffer-seatalk-bridge`) MUST
write its process id into the directory its bootloader unpacked it into (`$TMPDIR/_MEI*`) before
any Coffer code runs. A frozen daemon MUST, when it starts and every 6 hours after, delete each
such directory whose marked process no longer runs. It MUST NOT delete an unmarked directory —
another PyInstaller program's, or one whose process has not marked it yet — nor its own. The
bootloader removes the directory when its program exits, but not when the process is killed
outright, and each leftover is the size of the whole archive.

#### Scenario: a frozen daemon deletes the unpack directories of exited Coffer binaries
- **GIVEN** `$TMPDIR` holding a `_MEI*` directory marked with the pid of an exited Coffer process, one marked with a running process's pid, and one with no mark
- **WHEN** a frozen daemon starts
- **THEN** the directory of the exited process is deleted
- **AND** the other two, and the daemon's own unpack directory, are left as they were
