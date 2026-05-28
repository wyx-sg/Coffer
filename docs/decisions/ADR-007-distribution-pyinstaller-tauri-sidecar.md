# ADR-007: Distribution — PyInstaller-Bundled Daemon + Shim as Tauri Sidecars

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: spec `001-mcp-gateway` (FR-021, SC-009), [ADR-005](ADR-005-session-subprocess-model.md), [ADR-006](ADR-006-daemon-detect-or-spawn.md)

## Context

Coffer ships three runnable surfaces — the long-lived `coffer-daemon`, the
short-lived `coffer-mcp-shim` (spawned per MCP-client session), and a desktop
shell (Tauri) — and the project's target audience includes users without a
system Python install. Spec `001-mcp-gateway` commits to that audience in two
places:

- **FR-021** — "the end-user install path MUST produce a working coffer daemon
  and shim without requiring the user to install Python or other runtimes."
- **SC-009** — a user on a clean machine (no Python) reaches `status: ready`
  from a single distributable, with no manual setup beyond the installer.

That rules out anything that requires the user to install Python, manage a
virtualenv, or troubleshoot wheel build failures. We need to decide how the
Python code is packaged for end-user distribution.

The desktop shell is a separate question: when the Tauri bundle ships, it
needs to embed (or otherwise locate) the daemon + shim binaries. The Tauri 2
"sidecar" mechanism (`tauri.conf.json` → `bundle.externalBin`) is the
documented way to ship platform-native auxiliary binaries alongside the app.

## Decision

**Package the daemon and shim as single-file PyInstaller binaries; the desktop
bundle ships them as Tauri sidecars.**

Concrete choices:

- `backend/coffer-daemon.spec` builds `dist/coffer-daemon` (single-file
  executable). `backend/coffer-mcp-shim.spec` builds `dist/coffer-mcp-shim`.
- `make bundle-binaries` (`scripts/build_binaries.sh`) drives PyInstaller for
  the current host; the release CI matrix invokes it on macOS arm64+x64,
  Windows x64, and Linux x64+arm64 runners.
- Each spec pins the empirically-required `hiddenimports` for FastAPI,
  SQLAlchemy 2 / aiosqlite, Pydantic 2, `mcp`, `keyring`, and (daemon-only)
  Alembic. The hidden-import list is documented in `specs/001-mcp-gateway/research.md`.
- Alembic migrations are shipped as data files inside the daemon binary so the
  daemon can run `upgrade head` against a fresh DB on first launch.
- The shim binary deliberately excludes heavy daemon-only deps (FastAPI,
  uvicorn, SQLAlchemy, Alembic, structlog) to stay small — the shim only needs
  `httpx` to talk to the daemon over loopback HTTP.
- The desktop application is packaged separately as a Tauri 2 bundle (DMG /
  MSI / AppImage / deb). The PyInstaller binaries are wired in via
  `tauri.conf.json` `bundle.externalBin`; the shell discovers the daemon via
  `~/.coffer/daemon.json` ([ADR-006](ADR-006-daemon-detect-or-spawn.md)) rather than launching it directly,
  so the same binaries are reusable by the CLI and external MCP clients.
- The Tauri sidecar wiring lands with the desktop shell itself (planned in a
  follow-up UI spec). For spec `001-mcp-gateway` only the daemon + shim
  binaries ship; users on the CLI-only install path get a working daemon and
  shim without any desktop UI.

## Consequences

**Positive**

- Satisfies FR-021 + SC-009 on day one: `make bundle-binaries` produces two
  single-file executables that run on a clean machine with no Python.
- Distribution is uniform across platforms: the same PyInstaller spec works
  unchanged on macOS, Windows, and Linux (only the `--target-arch` and host
  matters).
- The shim binary stays small because it excludes server-side deps —
  important for MCP clients that re-spawn the shim per session.
- Tauri sidecars are the documented way to ship auxiliary binaries with a
  Tauri 2 app; we get DMG / MSI / AppImage / deb output from `tauri build`
  for free.
- Forward-compatible with a later "system service install" follow-on
  ([ADR-006](ADR-006-daemon-detect-or-spawn.md) operational follow-on): launchd / systemd / Windows service
  configs reference the same binary path.

**Negative**

- PyInstaller binaries are large (≈ 40–80 MB per binary on macOS, larger on
  Windows) because they embed the Python interpreter and a slice of stdlib.
  Acceptable for a developer-targeted desktop app; not acceptable for the
  shim if we ever scope down to embedded use.
- PyInstaller hidden-import discovery is empirical; first-time additions of
  new Python deps (especially Pydantic / SQLAlchemy upgrades) may require
  re-walking the import graph. Mitigated by pinning the list in
  `research.md` and `backend/coffer-*.spec` and by the bundle smoke test in CI.
- macOS Gatekeeper requires either notarization or `xattr -d
com.apple.quarantine` on first launch. Notarization is deferred (no Apple
  Developer account yet); the manual `xattr` step is documented in
  `specs/001-mcp-gateway/quickstart.md`.
- Bundling a Python interpreter means a Python security update requires a new
  Coffer release; this is the price of "no system Python required."

**Operational follow-on**

- CI release matrix produces six artifacts per release (macOS arm64 + x64
  universal, Windows x64, Linux x64 + arm64). Each runs a post-build smoke
  test (`scripts/smoke_test_bundle.sh`) that boots the bundled daemon to
  `status: ready` before publishing.
- The shim binary path is exposed to the user on first launch (either via the
  desktop UI when present, or via `coffer daemon status` for CLI-only users)
  so they can paste it into their MCP client's config.

## Alternatives Considered

**Require system Python 3.12+ and a venv (`pip install coffer`).** Rejected.

- Violates FR-021 and SC-009 by definition. Users on Windows and most
  designer / non-developer macOS users do not have a working Python install,
  let alone the version we require.
- Even on Linux, distribution-packaged Python is frequently a major version
  behind ours; users would hit obscure build failures on `aiosqlite` or
  `pydantic-core` wheels.
- The CLI-only developer install path (`pip install -e ./backend`) is still
  documented for contributors — but it is not the distribution channel for
  end users.

**Nuitka or PyOxidizer instead of PyInstaller.** Rejected for v0.

- PyInstaller has the broadest support for our dep set (FastAPI, SQLAlchemy
  async, `mcp`, `keyring` backends) and the most-documented hidden-imports
  recipes. Nuitka's AOT compilation is attractive but introduces a longer
  build cycle and platform-specific compiler dependencies in CI.
- Switching the bundler later is a contained, reversible change: nothing in
  the daemon's runtime contract depends on PyInstaller specifically.

**Tauri "embedded resources" instead of sidecars.** Rejected.

- Tauri's sidecar mechanism is precisely designed for "ship a native binary
  alongside the app"; using it preserves correct per-platform packaging
  (codesigning identity, `chmod +x` on Linux, Windows code-signing) and the
  ability to invoke the daemon via the OS rather than from inside the Tauri
  IPC layer.
- Embedded resources are appropriate for static assets, not executables.

**Two separate installers (Tauri desktop + PyInstaller binaries).** Rejected
for the headline UX but accepted as an implicit consequence for the
CLI-only path.

- For the desktop user the experience must be "drag the app to /Applications
  and you're done"; that means the daemon + shim binaries must be packaged
  inside the Tauri bundle. The sidecar mechanism delivers exactly that.
- For developer / CLI-only users, `pip install -e ./backend` remains the
  documented path; they bypass PyInstaller and the Tauri bundle entirely.
- A third standalone download of just the PyInstaller binaries (without the
  Tauri shell) may be offered post-v0 for headless server installs; not
  needed for the v0 spec.
