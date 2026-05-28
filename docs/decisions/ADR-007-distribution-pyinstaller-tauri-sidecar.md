# ADR-007: Distribution — PyInstaller-Bundled Daemon + Shim as Tauri Sidecars

**Status**: Accepted
**Date**: 2026-05-20 (revised 2026-05-28; see Revision history)
**Deciders**: Yuxing Wu
**Related**: `.specify/memory/constitution.md` (Languages), spec `001-mcp-gateway` (FR-021, SC-009), [ADR-006](ADR-006-daemon-detect-or-spawn.md)

## Context

Coffer has three runnable entry points: the long-lived `coffer-daemon`,
the per-MCP-session `coffer-mcp-shim`, and a desktop shell (Tauri). The
target user population includes users without a system Python install.
Spec `001-mcp-gateway` commits to this in two places:

- **FR-021** — "The end-user install path MUST produce a working coffer
  daemon and shim without requiring the user to install Python or other
  runtimes."
- **SC-009** — A user on a clean machine (no Python) reaches `status: ready`
  from a single distributable with no manual steps beyond clicking through
  the installer.

That rules out any approach that requires users to install Python,
maintain a virtualenv, or recover from wheel-build errors. We need to
decide how Python code is delivered to end users.

The desktop shell is a separate question: when the Tauri bundle lands,
it needs to embed (or otherwise locate) the daemon + shim binaries.
Tauri 2's sidecar mechanism (`bundle.externalBin` in `tauri.conf.json`)
is the official answer for "ship a native helper binary alongside an app".

## Decision

**PyInstaller-built daemon and shim, packaged as Tauri sidecars, with a
cross-platform CI release matrix.**

Concrete choices:

- `backend/coffer-daemon.spec` builds `dist/coffer-daemon` (single-file
  executable). `backend/coffer-mcp-shim.spec` builds `dist/coffer-mcp-shim`.
- `make bundle-binaries` (driven by `scripts/build_binaries.sh`) runs
  PyInstaller on the current host; the release CI matrix invokes the same
  script on macOS arm64 + x64, Linux x64, and Windows x64 runners.
- Each spec pins the `hiddenimports` empirically required at runtime —
  FastAPI, SQLAlchemy 2 / aiosqlite, Pydantic 2, `mcp`, `keyring`, and
  (daemon only) Alembic. The list is recorded in
  `specs/001-mcp-gateway/research.md`.
- Alembic migrations ship as data files inside the daemon binary so
  first-launch can run `upgrade head` against a fresh DB.
- The shim binary deliberately excludes server-side heavy dependencies
  (FastAPI, uvicorn, SQLAlchemy, Alembic, structlog) to keep its size
  manageable — the shim talks to the daemon over loopback HTTP and only
  needs `httpx`.
- The desktop app is built as a Tauri 2 bundle (DMG / MSI / AppImage / deb).
  The PyInstaller binaries are wired in via `bundle.externalBin` in
  `desktop/tauri.conf.json`. The shell discovers the daemon through
  `~/.coffer/daemon.json` (see [ADR-006](ADR-006-daemon-detect-or-spawn.md)) rather than spawning it
  directly, so the same pair of binaries can be reused by the CLI and by
  external MCP clients.
- On every launch, the desktop app deploys `coffer-mcp-shim` to a stable
  user-writable PATH location so MCP clients can resolve the
  `command: coffer-mcp-shim` config: macOS / Linux:
  `~/.coffer/bin/coffer-mcp-shim`; Windows:
  `%LOCALAPPDATA%\Coffer\bin\coffer-mcp-shim.exe` (falling back to
  `%USERPROFILE%\Coffer\bin\` when `%LOCALAPPDATA%` is unset). The
  POSIX path co-locates with the daemon's `~/.coffer/daemon.json` from
  [ADR-006](ADR-006-daemon-detect-or-spawn.md), which simplifies the
  user mental model ("everything Coffer lives under `~/.coffer/`"). The
  first launch prompts the user once if the directory is not yet on
  `PATH`.
- macOS Apple notarisation is deferred (requires a paid Apple Developer
  account). Users on macOS are instructed to clear quarantine on first
  launch with `xattr -d com.apple.quarantine /Applications/Coffer.app`.
  See [`docs/distribution/macos-notarization.md`](../distribution/macos-notarization.md)
  for the runbook to enable signing + notarization once secrets are in
  place.

## Consequences

**Positive**

- Satisfies FR-021 and SC-009 from day one: `make bundle-binaries`
  produces two single-file executables that run on a clean machine with
  no Python.
- Same binaries work for desktop launch, command-line invocation, and
  direct download. No multiple distribution paths to maintain.
- Cross-platform consistency: the same PyInstaller specs work on macOS,
  Windows, and Linux unchanged (only `--target-arch` differs per host).
- The shim binary stays small because it excludes server-side
  dependencies — important for MCP clients that re-spawn the shim
  every session.
- Tauri sidecars are the official Tauri 2 mechanism for shipping helper
  binaries; `tauri build` automatically produces DMG / MSI / AppImage / deb.
- Forward-compatible with optional "system service install" (an
  [ADR-006](ADR-006-daemon-detect-or-spawn.md) follow-up): launchd, systemd, and Windows service
  configs all point at the same binary paths.

**Negative**

- Bundle size ≈ 80–120 MB per platform (Python interpreter + httpx +
  SQLAlchemy + aiosqlite + keyring + Pydantic + structlog + Typer + …).
  Larger than a comparable native binary but acceptable for a
  developer-targeted desktop app.
- PyInstaller cold-start is ~500–800 ms (vs ~100 ms for system Python).
  The daemon starts once per OS-login and lives long; the shim starts
  once per MCP-client startup. Both fit within human-perceivable
  tolerance.
- Cross-platform CI maintenance overhead: every dependency upgrade must
  be validated on three OSes. Mitigated by reusing GitHub Actions matrix
  builds.
- macOS Gatekeeper friction until notarisation is added — see
  [`docs/distribution/macos-notarization.md`](../distribution/macos-notarization.md)
  for the path to enabling it. The current user-visible workaround is
  `xattr -d com.apple.quarantine /Applications/Coffer.app` on first
  launch.
- PyInstaller has known sharp edges around hidden imports (especially
  for Pydantic v2 and SQLAlchemy 2). Mitigation: explicit `hiddenimports`
  lists in the PyInstaller specs, validated by a CI smoke test
  ([`scripts/smoke_test_bundle.sh`](../../scripts/smoke_test_bundle.sh) — boots the bundled daemon to
  `status: ready` and exchanges a JSON-RPC `initialize` with the bundled
  shim).

**Operational follow-ups**

- The CI release matrix produces **six artifacts per release**:

  - macOS arm64 DMG
  - macOS x64 DMG
  - Linux x64 AppImage
  - Linux x64 .deb
  - Windows x64 MSI
  - Windows x64 NSIS (.exe)

  Counting by **target platform** the matrix is four (macOS arm64, macOS
  x64, Linux x64, Windows x64) — each produces one or two installer
  formats. The macOS artifacts are two **separate** per-architecture DMGs
  (we do not currently `lipo` them into a universal binary; doing so
  would add a post-processing step we have not committed to). Each
  installer ships with a SHA-256 checksum file.

- Before every release, each bundle runs a post-build smoke test
  ([`scripts/smoke_test_bundle.sh`](../../scripts/smoke_test_bundle.sh))
  — must boot the bundled daemon to `status: ready` and let the bundled
  shim exchange a JSON-RPC `initialize` over loopback. Cross-linked from
  spec 003 §Distribution.
- The shim binary path is exposed to the user on first launch (via the
  desktop UI when present; via `coffer daemon status` for CLI-only
  users) so it can be pasted into MCP-client config.

## Alternatives Considered

**Require system Python 3.12+ with a venv (`pip install coffer`).**
Rejected.

- Directly violates FR-021 and SC-009. Most macOS users with a designer /
  non-developer background, and most Windows users, do not have a working
  Python install at the required version.
- Even on Linux, distro-shipped Python is typically one major version
  behind ours; users hit wheel-build errors for `aiosqlite` or
  `pydantic-core`.
- The contributor-facing CLI-only path (`pip install -e ./backend`) stays
  in the docs — but it is not the end-user distribution channel.

**Nuitka or PyOxidizer instead of PyInstaller.** Rejected for v0.

- PyInstaller has the broadest support for our dependency set (FastAPI,
  SQLAlchemy async, `mcp`, `keyring` backends) and the largest community
  cookbook for hidden imports. Nuitka's AOT compilation is appealing
  but lengthens the build cycle and pulls platform-specific compilers
  into CI.
- Switching packager later is a bounded reversible change: nothing in
  the daemon's runtime contract is PyInstaller-specific.

**Tauri "embedded resources" instead of sidecars.** Rejected.

- The Tauri sidecar mechanism is designed for "ship a native binary
  alongside the app"; it preserves the correct per-platform packaging
  (codesign identity, `chmod +x` on Linux, Windows code signing) and the
  ability to spawn the daemon through the OS rather than through the
  Tauri IPC layer.
- Embedded resources are for static assets, not executables.

**Universal macOS binary (`lipo`).** Considered, deferred.

- A universal DMG would halve the macOS download count at the cost of
  doubling per-user download size and complicating the release matrix
  with a `lipo` post-processing step. Two separate per-arch DMGs is
  simpler and matches the current `release.yml` behavior.

**Two separate installers (Tauri desktop + PyInstaller binaries).** Rejected
at the main-UX layer but implicitly accepted for the CLI-only path.

- The desktop user experience must be "drag the app to /Applications and
  you're done"; that requires daemon + shim binaries inside the Tauri
  bundle. The sidecar mechanism provides this.
- For developers / CLI-only users, `pip install -e ./backend` remains the
  documented path; they entirely bypass PyInstaller and the Tauri bundle.
- Post-v0 we may publish a "binaries only" download (PyInstaller artifacts
  without the Tauri shell) for headless server installs; not needed in v0.

## Revision history

- **2026-05-20** — Initial decision (spec 001 era): PyInstaller + Tauri
  sidecar, universal macOS binary planned, shim path under
  `~/Library/Application Support/Coffer/bin/` on macOS.
- **2026-05-28** (PR #24) — Revised for spec 003 implementation reality:
  (a) two separate per-arch macOS DMGs instead of a universal binary
  (release pipeline does not run `lipo`); (b) shim path on macOS / Linux
  moved to `~/.coffer/bin/` to co-locate with `~/.coffer/daemon.json`
  from ADR-006; (c) explicit per-release artifact count (six installer
  files across four target platforms, each with a SHA-256 checksum);
  (d) cross-links to [`scripts/build_binaries.sh`](../../scripts/build_binaries.sh),
  [`scripts/smoke_test_bundle.sh`](../../scripts/smoke_test_bundle.sh),
  and the macOS notarization runbook restored.
