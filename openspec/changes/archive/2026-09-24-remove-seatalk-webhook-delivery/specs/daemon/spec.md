## MODIFIED Requirements

### Requirement: Own and reap the daemon's long-lived children
The daemon MUST spawn, record and terminate every long-lived child it owns — such as an agent
app-server — through one path: recording the child's pid is
inseparable from spawning it, and termination is one `SIGTERM` → bounded wait → `SIGKILL` → bounded
wait ladder whose pid record is dropped only because the child was reaped here. Each child's record
is one file naming its pid and command line. At startup the daemon MUST sweep what a previous crash
left behind: recorded children, and sibling daemon processes **provably serving this same vault**.
"Not provably ours" MUST mean "leave it alone" — a candidate whose vault cannot be read, or a
matching executable running against another `HOME`, MUST NOT be touched, because a wrong kill costs
somebody a running daemon while a missed one costs only a port the next start reports.

#### Scenario: the daemon reaps only the children it can prove are its own
- **GIVEN** a previous daemon crashed leaving a recorded long-lived child running, and another daemon binary is running against a different vault under a throwaway `HOME`,
- **WHEN** a daemon starts and runs its startup sweep,
- **THEN** the recorded orphan is terminated, and the daemon serving the other vault is left untouched — anything not provably serving this vault is left alone.

### Requirement: Refuse a request whose Host is not loopback
The daemon MUST refuse any request whose `Host` header does not name a loopback authority —
`127.0.0.1`, `localhost` or `::1`, with or without a port — answering `421` with error code
`HOST_NOT_LOOPBACK` instead of serving it. This is what makes "Hand the browser its token in the
served page" safe: binding to loopback (see "Bind every endpoint to loopback only") stops a remote
host, but not a **browser** on a page whose hostname an attacker re-resolves to `127.0.0.1` — DNS
rebinding, which the browser then treats as same-origin, so CORS does not apply. Rebinding does not
change the `Host` header, so a rebound request still names the attacker's own hostname and is
refused before it can read a token out of the served document. The rule MUST hold for every surface
the daemon exposes.

#### Scenario: a rebound page is refused before it can read the token
- **GIVEN** a page on an attacker-controlled origin whose hostname resolves to `127.0.0.1`, which the browser therefore treats as same-origin with the daemon,
- **WHEN** it fetches any daemon URL, including `/`,
- **THEN** the daemon refuses the request with `421 HOST_NOT_LOOPBACK` because the `Host` header still names the attacker's hostname — while the same request addressed to `127.0.0.1`, `localhost` or `::1` is served normally.

### Requirement: Write one bounded daemon log in one format
`~/.coffer/logs/daemon.log` MUST be the one file the daemon, the children it spawns, and every
surface writing on their behalf append to — one timeline rather than one file per writer, because
the question it answers is always "what else happened around then". The directory MUST be
relocatable through `COFFER_LOG_DIR` so a packaged or test install can put it elsewhere. The file
MUST be bounded by rotation rather than by deletion, and the retention sweep that ages out the
per-process and per-upstream log files MUST NOT delete it or its rotations: it is held open, and
deleting it would leave the daemon logging nowhere until the next restart.

Because several writers share it — Coffer's own structured JSON, uvicorn, a rich-rendered upstream,
some of it colour-escaped — the file is deliberately not one format, and every
reader of it is obliged to normalise rather than to assume (see "Serve the daemon log tail
normalised"). What the daemon *itself* writes, however, MUST be one format: every record produced
inside the daemon process — its own modules and the libraries logging alongside them, alembic and
asyncio included — MUST arrive as a single line carrying, at least, the instant the record was
created, its level, the logger that emitted it and the message, with a traceback kept inside the
record that raised it rather than spread across lines that state none of those. A library MUST NOT
be able to change that by configuring logging for its own purposes: the daemon owns its root logger
for its whole life, and any library configuration that would replace it is removed at the call site
rather than tolerated and parsed around. Each record MUST appear in the file exactly once — the file
is also the redirect target for the daemon's own stdout and stderr (see "Spawn a detached daemon
from any surface that needs one"), so a process writing to both that file and its stderr would
record everything twice and make one event read as two.

#### Scenario: every line the daemon writes carries the same fields
- **GIVEN** a configured daemon, and a record emitted on an ordinary logger — one of Coffer's own modules, or a library's such as `alembic.runtime.migration` — after a migration has already run,
- **WHEN** `daemon.log` is read back,
- **THEN** that record is one line stating the instant it was created, its level, its logger and its message, and a record logged with an exception carries the traceback inside that same line rather than as lines stating none of those,
- **AND** the record appears exactly once, even though the detached daemon's own stderr is that same file.

### Requirement: Release the macOS arm64 terminal archive
The release pipeline MUST produce, per `v*` tag, the **terminal-install tier** for **macOS arm64
only**: a `coffer-cli-<triple>.tar.gz` archive containing exactly three binaries: `coffer` (the
management CLI), `coffer-daemon` and `coffer-mcp-shim`. The binaries MUST stay co-located inside the archive so the frozen resolution
of "Spawn a detached daemon from any surface that needs one" finds `coffer-daemon` next to
`coffer`. macOS x64 (Intel), Linux and Windows are deliberately not built — those legs were never
validated end to end. This archive carries the "no system Python required" promise on its own: on a
machine with no system Python, extracting it and running `coffer daemon start` reaches
`status: ready`, and `coffer open` renders the UI authenticated. Both tiers ship per tag: this
archive is the terminal install, and the `.dmg` of [desktop-app](../desktop-app/spec.md) "Ship the desktop tier as a macOS arm64 dmg" is the double-click one;
neither is a substitute for the other.

#### Scenario: release tag produces the CLI archive and SHA256SUMS
- **GIVEN** a release tag matching `v*` is pushed,
- **WHEN** the release workflow finishes,
- **THEN** the release contains the terminal tier — `coffer-cli-<triple>.tar.gz` for macOS arm64, holding `coffer`, `coffer-daemon` and `coffer-mcp-shim`, co-located, and no other binary,
- **AND** the release contains a single aggregated `SHA256SUMS` file covering every artifact of every tier, including the desktop tier of [desktop-app](../desktop-app/spec.md) "Ship the desktop tier as a macOS arm64 dmg",
- **AND** no other platform is built.

### Requirement: Deploy frozen sibling binaries and back up the vault before migrating
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

Before `alembic upgrade head` changes an on-disk `coffer.db`, the daemon MUST copy it (and any
`-wal`/`-shm` companions) to `coffer.db.pre-<revision>`, keeping the three newest copies; an
already-current schema or an in-memory database MUST NOT be copied. A source install MUST NOT do
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

#### Scenario: a schema upgrade keeps a copy of the vault
- **GIVEN** a daemon starting against a `coffer.db` whose Alembic revision is behind this build's head,
- **WHEN** the migrations run at startup,
- **THEN** `coffer.db.pre-<revision>` (with its `-wal`/`-shm` companions, when present) holds the pre-upgrade state beside the live file, only the three newest such copies are kept, and a start against an already-current schema — or an in-memory database — copies nothing.
