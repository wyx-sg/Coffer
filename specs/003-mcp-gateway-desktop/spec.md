# Feature Specification: Desktop Shell & Distribution

**Feature Branch**: `feature/003-mcp-gateway-desktop` (on top of `feature/002-mcp-gateway-web`)
**Status**: Draft
**Input**: 002-ui-shell delivered the web UI and explicitly deferred two acceptance scenarios from spec 002's User Story 5 (desktop shell): launch-at-login and close-to-tray. This spec owns those scenarios and the Tauri desktop wrapper + distribution pipeline that makes them work.

**Scope note**: Coffer's user-facing UI lives in 002-ui-shell (web shell, visual language, information architecture). This spec adds the **desktop wrapper** — Tauri 2 shell, daemon supervision, tray icon, autostart plugin, PyInstaller sidecar packaging, and the macOS notarization release pipeline. It introduces no new resource kinds and no new UI screens; the web UI from 002 renders inside the Tauri window with the desktop-only `AppSettings` component activating behind the `isTauri()` guard that 002 already wired up.

## User Scenarios & Testing

### User Story 1 — Desktop shell: always-on and out of the way (Priority: P3)

After initial setup, the developer expects Coffer to be present whenever any MCP client starts — no manual launch — and to stay out of the way when they are not actively managing it. The Tauri desktop app supervises the local daemon (starting it and reconnecting transparently), runs in the system tray, restores its window from the tray on click, and offers optional launch-at-login.

**Why this priority**: P3 — quality-of-life polish. The daemon and shim (spec 001) work without the desktop app; this story is the convenience layer that makes Coffer a daily-driver desktop product. Inherited from spec 002 §User Story 5, where launch-at-login and close-to-tray were explicitly deferred to this spec.

**Independent Test**: enable "launch at login", log out and back in — the daemon is running and the tray icon is present. Close the main window — the daemon stays alive, the tray icon remains, and an MCP client still works; reopening from the tray shows the same state.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- launch at login
- close to tray, not exit

---

### User Story 2 — Single-bundle install (Priority: P3)

A developer downloads one installer from the GitHub Releases page for their platform and ends up with a working Coffer — no system Python, no separate daemon install, no manual PATH editing for the shim. The Tauri bundle carries both `coffer-daemon` and `coffer-mcp-shim` as PyInstaller-built sidecars; first launch deploys the shim to a stable user-writable PATH location and the daemon comes up on its own.

**Why this priority**: P3 — distribution is the gate that turns the local-dev product into something a teammate or open-source contributor can try without cloning the repo. Without single-bundle install, the desktop shell from US1 has no audience.

**Independent Test**: on a clean machine (no Python, no Coffer checkout), download the platform installer from a draft release, install it, launch it once; verify the daemon reaches `status: ready` and `coffer-mcp-shim` resolves from a fresh shell.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- release tag produces the platform artifact matrix
- post-build smoke test boots shim and gets JSON-RPC reply

---

### User Story 3 — Daemon auto-supervision (Priority: P3)

The user opens the desktop app and expects "the daemon is running" to be true without thinking about it. If the daemon is already running (because another entry point — CLI or shim — started it), the desktop shell connects to it. If it is not, the shell spawns it as a detached process that survives the desktop window closing. The user can also explicitly restart the daemon from the desktop UI if something has gone wrong.

**Why this priority**: P3 — the detect-or-spawn pattern is owned by [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md); this story is the desktop shell's responsibility to apply it correctly so the daemon outlives the GUI.

**Independent Test**: with the daemon already running (e.g., started by `coffer daemon start`), launch the desktop app — it connects without spawning a duplicate. Quit the desktop app — the daemon is still reachable. With no daemon running, launch the desktop app — it spawns the daemon, which survives a subsequent desktop-app close.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- desktop shell connects to an already-running daemon without duplicating it
- desktop shell spawns the daemon when none is running and the daemon survives close
- restart daemon from the tray/app menu

---

### User Story 4 — Shim auto-deploy to PATH (Priority: P3)

The user pastes a vendor's MCP-client config snippet (`"command": "coffer-mcp-shim"`) and it resolves without telling them what path to use. Every desktop launch idempotently deploys the bundled `coffer-mcp-shim` binary to a stable user-writable directory on `PATH` (macOS / Linux: `~/.coffer/bin/`; Windows: `%LOCALAPPDATA%\Coffer\bin\`); a size-mismatch heuristic re-copies the binary when the bundle has been upgraded, and a no-op when nothing changed.

**Why this priority**: P3 — shim discoverability is what makes the MCP-client config snippets in the README portable across users without per-machine parameterisation.

**Independent Test**: launch the desktop app on a fresh install; verify `which coffer-mcp-shim` resolves to the expected directory; launch again with no version change — verify the on-disk binary is untouched (mtime / size unchanged); upgrade the bundle — verify the on-disk binary is replaced.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- first launch deploys shim to user PATH
- subsequent launch is idempotent (no-op when shim already up to date)
- upgraded bundle triggers shim re-deploy via size-mismatch heuristic

---

### User Story 5 — Tray menu actions (Priority: P3)

The user clicks the tray icon and expects a small, obvious menu — open the main window, restart the daemon, quit. "Quit" actually quits (does not hide-to-tray a second time); restart bounces the daemon cleanly; open restores the hidden window.

**Why this priority**: P3 — the tray icon is the user's only handle on a running Coffer when the main window is closed. Without explicit quit, the only way to stop Coffer is the OS process manager.

**Independent Test**: close the main window (hides to tray); click the tray "Open" — main window restores. Click "Restart daemon" — daemon process restarts, reachable on the same daemon.json port. Click "Quit" — the Coffer process exits, tray icon disappears, and no daemon survives.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- tray menu open restores the hidden window
- tray menu quit exits the desktop app via app.exit()
- tray menu restart bounces the daemon process

---

### Edge Cases

- **Shim size-mismatch heuristic** — the auto-deploy compares the bundled shim's byte size against the on-disk shim before copying. Equal size → no-op. Differing size → atomic replace. This catches version upgrades without needing a separate version-stamp file.
- **Windows shim PATH fallback** — when `%LOCALAPPDATA%` is unset (rare; usually only in non-interactive service contexts), the shim deploy falls back to `%USERPROFILE%\Coffer\bin\` and emits a one-line log entry. The desktop app continues to launch.
- **Bundled-shim search probes parent directories** — Tauri bundle layout differs between dev (`target/debug/`) and release (`Resources/`). The shim-deploy step probes both the sidecar directory and its parent so the same code works in both.
- **Tray icon fallback to embedded PNG** — if the platform-preferred tray icon (e.g., template-tinted macOS PNG) fails to load, the desktop shell falls back to a single embedded PNG so the tray menu is never invisible.

## Acceptance Scenarios

The scenarios below cover this spec's user stories. Scenarios `launch at login` and `close to tray, not exit` are imported verbatim from `specs/002-ui-shell/spec.md` per the audit-traceability annotation there. They cover US1 (desktop shell — launch-at-login, close-to-tray). The desktop spec's acceptance audit owns them from here on. Build-pipeline scenarios cover US2 (single-bundle install).

### Scenario: launch at login

- **Given** the user has enabled launch-at-login in settings
- **When** the user logs back into their machine
- **Then** Coffer starts in the background and the system tray icon appears

### Scenario: close to tray, not exit

- **Given** Coffer is running with the main window open
- **When** the user closes the window
- **Then** the window hides, the daemon and tray icon remain, and any MCP client can still use coffer; reopening the window from the tray shows the same state

### Scenario: release tag produces the platform artifact matrix

- **Given** a release tag is pushed (matching `v*`)
- **When** `.github/workflows/release.yml` finishes
- **Then** the release contains four installer artifacts — macOS arm64 DMG, macOS x64 DMG, Linux x64 (AppImage/deb), Windows x64 (MSI/NSIS)
- **And** each installer ships with a SHA-256 checksum file alongside it

### Scenario: post-build smoke test boots shim and gets JSON-RPC reply

- **Given** a freshly built bundle from the release matrix
- **When** the post-build smoke test (`scripts/smoke_test_bundle.sh`) is run against it
- **Then** the bundled `coffer-mcp-shim` starts, exchanges a JSON-RPC `initialize` message with the bundled daemon, and exits with status 0

## Functional Requirements

- **FR-D01**: The Tauri 2 shell MUST host the 002 web UI inside its window; desktop-only UI affordances activate behind the `isTauri()` guard already wired in spec 002.
- **FR-D02**: The desktop shell MUST supervise the daemon using the detect-or-spawn pattern from [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md) — connect to an existing daemon by reading `~/.coffer/daemon.json`, or spawn `coffer-daemon` as a detached process (`setsid` on POSIX, `DETACHED_PROCESS` on Windows) when none is reachable. The spawned daemon MUST survive the desktop window closing.
- **FR-D03**: The desktop shell MUST display a system-tray icon at all times while the app is running. The tray menu MUST include at least "Open", "Restart daemon", and "Quit" items.
- **FR-D04**: A window-close event MUST be intercepted and translated into a hide-to-tray action; closing the main window MUST NOT terminate the desktop process.
- **FR-D05**: Selecting "Quit" from the tray MUST call `app.exit()` (or platform-equivalent) so the desktop process actually exits and the tray icon disappears.
- **FR-D06**: The desktop shell MUST integrate `tauri-plugin-autostart` with set/get capabilities so the `AppSettings` desktop tab can toggle launch-at-login and reflect the current state.
- **FR-D07**: On every launch, the desktop shell MUST idempotently deploy the bundled `coffer-mcp-shim` to a stable user-writable PATH directory (macOS/Linux: `~/.coffer/bin/`; Windows: `%LOCALAPPDATA%\Coffer\bin\`, with `%USERPROFILE%\Coffer\bin\` as fallback when unset). Deploy MUST be idempotent — equal-size on-disk binary is left untouched; differing-size triggers atomic replace.
- **FR-D08**: The Tauri bundle MUST declare `coffer-daemon` and `coffer-mcp-shim` as PyInstaller sidecars via `bundle.externalBin` in `desktop/tauri.conf.json`. No system Python dependency at runtime.
- **FR-D09**: The release pipeline MUST produce, per `v*` tag, four installer artifacts: macOS arm64 DMG, macOS x64 DMG, Linux x64 (AppImage / deb), Windows x64 (MSI / NSIS).
- **FR-D10**: Each release artifact MUST be accompanied by a SHA-256 checksum file generated in CI.

## Success Criteria

- **SC-D01**: Cold-start budget — from desktop-app launch to the main window first paint is under 3 seconds on a 2022 MacBook Air (Apple silicon) when the daemon is not yet running; under 1 second when the daemon is already running.
- **SC-D02**: Bundle size budget — each platform installer is under 200 MB. Current observed range is 90–150 MB (PyInstaller interpreter + httpx + SQLAlchemy + aiosqlite + keyring + Pydantic + structlog + Typer + Tauri frontend).
- **SC-D03**: Every Acceptance Scenario in this document is covered by at least one test marked with `acceptance(spec="003-mcp-gateway-desktop", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-D04**: The post-build smoke test (`scripts/smoke_test_bundle.sh`) runs against every artifact in the release matrix and returns success — bundled shim talks to bundled daemon over loopback HTTP and gets a JSON-RPC `initialize` reply.

## Distribution

The desktop app ships as a Tauri 2 bundle that wraps the headless daemon as a PyInstaller-built sidecar binary. See [`docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md`](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md) for the architectural decision and [`docs/distribution/macos-notarization.md`](../../docs/distribution/macos-notarization.md) for the macOS notarization runbook.

The release pipeline (`.github/workflows/release.yml`) runs PyInstaller per target architecture, drops the binary into `desktop/binaries/`, builds the Tauri bundle, notarizes (macOS, once a paid Apple Developer ID is in place), and uploads the artifact with its SHA-256 checksum.
