# Distribution — Three PyInstaller Binaries, Shipped as a CLI Archive and a Desktop App

**Status**: Accepted
**Date**: 2026-09-12
**Deciders**: Yuxing Wu
**Related**: [The Desktop Shell Hosts the Shared Frontend](desktop-shell-over-a-shared-frontend.md), [Daemon Detect-or-Spawn](daemon-detect-or-spawn.md), [Stdio Shim Bridge](stdio-shim-bridge.md), [Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md), [principles](../../docs-site/architecture/principles.md), [architecture: distribution](../../docs-site/architecture/distribution.md), spec daemon "Release the macOS arm64 terminal archive", spec daemon "Deploy frozen sibling binaries and back up the vault before migrating", spec desktop-app "Ship the desktop tier as a macOS arm64 dmg", PRs #317, #376, #386

## Context

Coffer is Python: a long-lived daemon (FastAPI, SQLAlchemy/aiosqlite, Alembic,
`mcp`, `keyring`, the channel SDKs), a stdio shim every MCP client spawns per
session, and a `coffer` management CLI. The people it is for include developers
without the Python version it needs, and people who have never opened a terminal
at all. A user on a clean machine must reach a running daemon from one download
with nothing installed first.

Three more forces shape the answer:

- **Binaries must find each other.** An MCP client config names
  `coffer-mcp-shim`; the shim auto-spawns `coffer-daemon` from beside itself
  after a reboot ([Daemon Detect-or-Spawn](daemon-detect-or-spawn.md)); the CLI
  does the same. So all three must land at stable absolute paths, together.
- **Two kinds of user.** A terminal user wants a `curl | sh` and a directory on
  `PATH`. Everyone else wants a double-click app ([The Desktop Shell Hosts the
  Shared Frontend](desktop-shell-over-a-shared-frontend.md)).
- **No paid Apple Developer ID.** Nothing Coffer ships can be signed or
  notarised today.

## Options Considered

### Packaging the Python

#### Option A — PyInstaller single-file executables (chosen)

`backend/coffer-daemon.spec`, `backend/coffer-mcp-shim.spec` and
`backend/coffer.spec` each freeze one entry point into a single-file binary;
`scripts/build_binaries.sh` (`make bundle-binaries`) runs all three into `dist/`.
The daemon spec carries its Alembic migrations and the built web UI
(`frontend/dist`, shipped as `webui/`) as data files, and pins the modules
imported lazily inside functions — `markitdown` and its document parsers,
`openai`, `langgraph`, `langchain` — in `hiddenimports`, because PyInstaller's
static analysis cannot see them. The shim spec excludes the server stack
(FastAPI, uvicorn, SQLAlchemy, Alembic, structlog) since it only needs `httpx`
to reach the daemon over loopback, and every spec excludes the heavy ML stack
(`torch`, `scipy`, …) as a guard — a transitive pull would take a binary from
about 95 MB to about 260 MB.

Pros: the broadest support for this dependency set (Pydantic 2, SQLAlchemy 2
async, `keyring` backends) and the largest cookbook of hidden-import fixes; no C
compiler in CI; nothing in the daemon's runtime contract depends on it, so a
later switch is bounded. Cons: binaries of roughly 100 MB; a cold start that
unpacks the archive (acceptable for a daemon that starts once per login, noticed
on the shim); and the sharp edge that a missing import or data path passes every
test and fails only in the frozen build. That edge is fenced by two gates:
`scripts/check_pyinstaller_specs.py` (`make lint`) fails when a spec's entry
script or `datas` path no longer exists, or when an `EXE` loses the frozen
`-X utf8` option (without it a binary started from Finder or launchd with no
`LANG` falls back to ASCII); and `scripts/smoke_test_bundle.sh`, run by the
release workflow on the built `dist/`, boots the frozen daemon under an isolated
`HOME` to a live `/daemon/status`, requires it to serve the bundled web UI, and
exchanges a JSON-RPC `initialize` with the frozen shim. It wins on dependency
coverage at the lowest build cost.

#### Option B — `pip install` / `pipx install` / `uv tool install`

Publish a wheel and let the user's Python install it. Pros: no freezing, small
downloads, instant upgrades. Cons: requires the right Python (3.12) on the
machine, which most of the audience does not have; distro Pythons lag and hit
wheel builds for `pydantic-core` or `aiosqlite`; and the resulting console
scripts live wherever that Python's `bin` is, not at the stable paths MCP
configs and the shim's sibling probe need. It stays the contributor path
(`pip install -e ./backend`, spec daemon "Install the console scripts from
source") and loses as the end-user path.

#### Option C — Nuitka

Compile Python to C and link a native binary. Pros: faster start, harder to
unpack. Cons: a C toolchain in CI, much longer builds (and PyInstaller already
costs most of a release's wall time), and a thinner record with this async
stack. It loses on build cost for a start-up gain the daemon does not need.

#### Option D — PyOxidizer

Embed the interpreter and load modules from memory. Pros: one static binary,
fast import. Cons: many packages that assume a real filesystem (`__file__`,
package data such as Alembic's templates and `mcp`'s resources) need special
handling, and the project's development has largely stopped. It loses on
maintenance risk.

#### Option E — Briefcase

BeeWare's app packager. Pros: produces a proper `.app`/installer per platform.
Cons: it packages *an application*, not a set of command-line binaries at stable
paths; the CLI and shim would still need a separate story, and the desktop app
is already Tauri. It loses because it solves the half of the problem that is
already solved.

#### Option F — An Electron app carrying an embedded Python

Bundle a Python runtime and the source inside an Electron shell. Pros: one
installer for the GUI. Cons: two runtimes (Chromium/Node and Python), several
hundred MB, and still no CLI on `PATH` for MCP clients. It loses on size and
because the terminal tier would still need Option A.

### How many download tiers

#### Option G — Two tiers built from one freeze: a CLI archive and a desktop `.dmg` (chosen)

Per `v*` tag, `.github/workflows/release.yml` (one leg, `macos-14`,
`aarch64-apple-darwin`) freezes the three binaries once and wraps them twice:

- `coffer-cli-aarch64-apple-darwin.tar.gz` holding `coffer`, `coffer-daemon`
  and `coffer-mcp-shim` under their plain names, installed by
  `curl … install.sh | sh` (served from `docs-site/public/install.sh`) into
  `~/.coffer/bin`, which it adds to `PATH` (overridable with
  `COFFER_INSTALL_DIR`, `COFFER_VERSION`, `COFFER_NO_MODIFY_PATH`);
- `Coffer-unsigned-aarch64-apple-darwin.dmg`, the Tauri app with the **same
  three files** copied from `dist/` into `desktop/binaries/` as `externalBin` —
  a copy, not a second PyInstaller run.

One aggregated `SHA256SUMS` covers both (spec daemon "Publish one aggregated
checksum file"). The `.dmg` needs nothing installed beforehand, and installing
it installs the CLI too, without the shell doing anything: the first daemon it
starts deploys all three binaries into `~/.coffer/bin/` (below). Pros: each kind
of user gets the install they expect; the expensive half (freezing) is done once,
so the second tier costs one Tauri build in CI; the app and the archive cannot
disagree about the binaries. Cons: a Rust toolchain in the release job, and an
unsigned `.dmg` is treated worse by Gatekeeper than a `curl`-downloaded archive.

#### Option H — One tier: the CLI archive only

The shape between PR #317 and PR #376. Pros: one artifact, no Rust, and a
`curl`-downloaded file is never quarantined. Cons: an app that requires the
terminal first is not an answer for the people the desktop shell exists for.
It loses because the second tier costs a Tauri build, not a second freeze.

#### Option I — The desktop app as an optional layer over an installed CLI

Ship a `.dmg` without the binaries and require the CLI first. Pros: a build of
minutes rather than most of an hour, and the binaries arrive unquarantined via
`curl`. Cons: needing the CLI first is a permanent second product for exactly
the user the app is for. It loses; the quarantine step is one documented command.

### Signing

#### Option J — Unsigned, with the quarantine step documented (chosen, for now)

Nothing is signed. A browser-downloaded `.dmg` carries `com.apple.quarantine`
and macOS refuses the app as damaged until the user runs
`xattr -dr com.apple.quarantine /Applications/Coffer.app`; a manually extracted
archive needs the same on `~/.coffer/bin`. `README.md` and the release notes
carry both commands (spec desktop-app "Document clearing the quarantine
attribute"). Pros: free, and it ships today. Cons: a real first-run hurdle,
worst on the desktop tier.

#### Option K — Developer ID signing and notarisation

Pros: the app opens on double-click; the right end state. Cons: requires a paid
Apple Developer account, which does not exist. It is not rejected on merit; it
is the single highest-value thing that account would buy, and the release job
has no signing step until then.

## Decision

**Coffer freezes `coffer`, `coffer-daemon` and `coffer-mcp-shim` with
PyInstaller once per release on macOS arm64, and publishes them twice: as
`coffer-cli-<triple>.tar.gz` and inside the unsigned `Coffer-unsigned-<triple>.dmg`,
under one `SHA256SUMS`.** Rules that follow:

- **The daemon deploys its siblings; nothing else does.** On a frozen start,
  `deploy_frozen_sidecars` (`backend/coffer/application/binary_deploy.py`,
  called from the daemon's lifespan in `surfaces/http/app.py`) copies the three binaries into
  `~/.coffer/bin/<version>/` with a temp-copy-then-rename and flips the public
  `~/.coffer/bin/<name>` symlinks onto that directory atomically. Staleness is
  byte size plus a version sentinel written after the copy — not mtime, which
  re-copied everything after a same-release reinstall. The newest two version
  directories are kept (`KEEP_VERSIONS`) so the last upgrade can be undone by
  pointing the links back, and a public link into a version directory under a
  name the build no longer ships is removed. Before PR #386 the deploy
  overwrote `~/.coffer/bin/<name>` in place, so a bad build replaced the only
  copy. The daemon owns this because it is the one process every frozen
  install starts, whichever tier it came from; the desktop shell is forbidden
  from writing `~/.coffer/bin/` (spec desktop-app "Reimplement no daemon route
  in the shell"). A source install skips it — `pip` already put the scripts on
  `PATH`.
- **The release channel is stamped before the freeze.** On a tag,
  `scripts/stamp_channel.py stable` rewrites `backend/coffer/build_channel.py`
  before `build_binaries.sh` runs, because PyInstaller freezes the module as it
  is ([Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md)).
- **The desktop leg reuses the CLI leg's binaries.** No second PyInstaller run.
- **The spec files stay honest.** A path a spec names must exist and every
  `EXE` keeps `-X utf8` (`check_pyinstaller_specs.py`); the release refuses to
  publish if the smoke test fails or the `.dmg` is missing.
- **macOS arm64 only.** Intel, Linux and Windows were dropped from the release
  matrix because they were never validated end to end. The specs are
  platform-neutral, so re-adding a leg is a CI and validation job, not a
  packaging redesign.

## Consequences

- A user with no Python reaches a running daemon from either download, and the
  paths every client uses (`~/.coffer/bin/<name>`, next to
  `~/.coffer/daemon.json`) are the same whichever tier they came from.
- The web UI travels inside the daemon binary as data; the `.dmg` hosts the same
  `frontend/dist` as a local asset. There is still one UI build.
- Every dependency upgrade must be proven on a frozen build, not only on the
  source tree; the smoke test and the spec checker are what catch it before a
  user does.
- A local `make desktop` takes roughly 50 minutes because it freezes all three
  binaries first; the release pays the freeze once for both tiers.
- Until an Apple Developer ID exists, every install starts with a quarantine
  command, and the desktop tier is where it hurts most.
