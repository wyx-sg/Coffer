# Feature Specification: Desktop Shell & Distribution

**Feature Branch**: `feature/003-mcp-gateway-desktop` (on top of `feature/002-mcp-gateway-web`)
**Status**: Accepted
**Input**: 002-ui-shell delivered the web UI and explicitly deferred the close-to-tray acceptance scenario from spec 002's User Story 5 (desktop shell). This spec owns that scenario and the Tauri desktop wrapper + distribution pipeline that makes it work.

**Scope note**: Coffer's user-facing UI lives in 002-ui-shell (web shell, visual language, information architecture). This spec adds the **desktop wrapper** — Tauri 2 shell, daemon supervision, tray icon, PyInstaller sidecar packaging, and a notarisation-ready macOS release pipeline (actual code-signing / notarisation is deferred until an Apple Developer ID is available; the workflow ships unsigned bundles until then). It introduces no new resource kinds and no new UI screens; the web UI from 002 renders inside the Tauri window.

## User Scenarios & Testing

### User Story 1 — Desktop shell: always-on and out of the way (Priority: P3)

After initial setup, the developer expects Coffer to be present whenever any MCP client starts — no manual launch — and to stay out of the way when they are not actively managing it. The Tauri desktop app supervises the local daemon (starting it and reconnecting transparently), runs in the system tray, and restores its window from the tray on click.

**Why this priority**: P3 — quality-of-life polish. The daemon and shim (spec 001) work without the desktop app; this story is the convenience layer that makes Coffer a daily-driver desktop product. Inherited from spec 002 §User Story 5, where close-to-tray was explicitly deferred to this spec.

**Independent Test**: Close the main window — the daemon stays alive, the tray icon remains, and an MCP client still works; reopening from the tray shows the same state.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- close to tray, not exit

---

### User Story 2 — Two download tiers (Priority: P3)

A user picks the download that fits their environment. Coffer ships **macOS (Apple Silicon) only** today; the release offers **two tiers**, both built from the same PyInstaller binaries:

1. **CLI-only** — a single archive `coffer-cli-<triple>.tar.gz` (macOS arm64) containing `coffer` (the management CLI), `coffer-daemon`, and `coffer-mcp-shim`. For headless / no-GUI installs: extract it, run `coffer-daemon` (or `coffer daemon start`), put `coffer-mcp-shim` on `PATH`, and point MCP clients at the shim. No desktop app required. All three binaries must stay co-located so the frozen detect-or-spawn logic (ADR-006) can find `coffer-daemon` next to `coffer`.
2. **CLI+desktop** — the Tauri bundle (macOS arm64 `.dmg`) that embeds `coffer-daemon` and `coffer-mcp-shim` as sidecars plus the desktop shell and the 002 web UI. One installer, no system Python, no separate daemon install, no manual PATH editing — first launch deploys the shim to a stable user-writable PATH location and the daemon comes up on its own.

**Why this priority**: P3 — distribution is the gate that turns the local-dev product into something a teammate or open-source contributor can try without cloning the repo. The CLI-only tier serves servers and headless boxes; the CLI+desktop tier serves daily-driver desktop users. Without either, the desktop shell from US1 has no audience.

**Independent Test**: CLI-only — on a clean machine (no Python, no Coffer checkout), download `coffer-cli-<triple>`, extract, run `coffer-daemon`, and verify a fresh shell resolves `coffer-mcp-shim` after it is placed on `PATH`. CLI+desktop — download the macOS `.dmg` from a draft release, install it, launch it once; verify the daemon reaches `status: ready` and `coffer-mcp-shim` resolves from a fresh shell.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- release tag produces both the CLI-only archives and the desktop installers
- post-build smoke test boots shim and gets JSON-RPC reply

---

### User Story 3 — Daemon auto-supervision (Priority: P3)

The user opens the desktop app and expects "the daemon is running" to be true without thinking about it. If the daemon is already running (because another entry point — CLI or shim — started it), the desktop shell connects to it. If it is not, the shell spawns it as a detached process that survives the desktop window closing. The user can also explicitly restart the daemon from the desktop UI if something has gone wrong.

**Why this priority**: P3 — the detect-or-spawn pattern is owned by [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md); this story is the desktop shell's responsibility to apply it correctly so the daemon outlives the GUI.

**Independent Test**: with the daemon already running (e.g., started by `coffer daemon start`), launch the desktop app — it connects without spawning a duplicate. Quit the desktop app — the daemon is still reachable. With no daemon running, launch the desktop app — it spawns the daemon, which survives a subsequent desktop-app close.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- desktop shell connects to an already-running daemon without duplicating it
- desktop shell spawns the daemon when none is running and the daemon survives close
- restart daemon from the tray menu or the desktop UI (the daemon-offline banner's Restart control — both call the same rate-limited `restart_daemon` command)

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

The user clicks the tray icon and expects a small, obvious menu — open the main window, restart the daemon, and quit. "Quit" actually quits the desktop app (does not hide-to-tray a second time); open restores the hidden window; "Restart daemon" bounces the daemon through the same rate-limited `restart_daemon` command the daemon-offline banner uses. Quit exits the GUI only: the daemon is a detached process and keeps running, so MCP clients still work after Quit.

**Why this priority**: P3 — the tray icon is the user's only handle on a running Coffer when the main window is closed. Without explicit quit, the only way to stop the desktop app is the OS process manager.

**Independent Test**: close the main window (hides to tray); click the tray "Open" — main window restores. Click "Restart daemon" — the daemon restarts and is reachable again on the daemon.json port. Click "Quit" — the desktop (Coffer GUI) process exits and the tray icon disappears; the detached daemon keeps running and an MCP client still works.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- tray menu open restores the hidden window
- tray menu restart bounces the daemon via the rate-limited restart command
- tray menu quit exits the desktop app via app.exit() while the daemon keeps running

---

### Edge Cases

- **Shim staleness heuristic (3 signals)** — the auto-deploy treats the on-disk shim as stale when ANY of three signals differ from the bundled shim: (1) byte size, (2) bundled mtime newer than the deployed mtime, or (3) the `.coffer-mcp-shim.version` sentinel content differs from the current app version. A missing target or missing sentinel also forces a copy; otherwise it is a no-op. The replace is atomic: the bundled binary is copied to a temp sibling in the same directory (made executable first on Unix) and then renamed over the target, so a crash or a concurrently executing shim never observes a truncated binary. The version sentinel catches the case where two builds produce a same-size binary across versions, which a pure size check would miss.
- **Windows shim PATH fallback** — when `%LOCALAPPDATA%` is unset (rare; usually only in non-interactive service contexts), the shim deploy falls back to `%USERPROFILE%\Coffer\bin\` and emits a one-line log entry. The desktop app continues to launch.
- **Bundled-shim search probes parent directories** — Tauri bundle layout differs between dev (`target/debug/`) and release (`Resources/`). The shim-deploy step probes both the sidecar directory and its parent so the same code works in both.
- **Tray icon fallback to embedded PNG** — if the platform-preferred tray icon (e.g., template-tinted macOS PNG) fails to load, the desktop shell falls back to a single embedded PNG so the tray menu is never invisible.

## Acceptance Scenarios

The scenarios below cover this spec's user stories. Scenario `close to tray, not exit` is imported verbatim from `specs/002-ui-shell/spec.md` per the audit-traceability annotation there. It covers US1 (desktop shell — close-to-tray). The desktop spec's acceptance audit owns it from here on. Build-pipeline scenarios cover US2 (single-bundle install).

### Scenario: close to tray, not exit

- **Given** Coffer is running with the main window open
- **When** the user closes the window
- **Then** the window hides, the daemon and tray icon remain, and any MCP client can still use coffer; reopening the window from the tray shows the same state

### Scenario: release tag produces both the CLI-only archive and the desktop installer

- **Given** a release tag is pushed (matching `v*`)
- **When** `.github/workflows/release.yml` finishes
- **Then** the release contains the macOS arm64 desktop bundle — an unsigned `.dmg` (named `*-unsigned.dmg`) plus a zipped `Coffer-unsigned-<triple>.app.zip`
- **And** the release also contains the CLI-only archive — `coffer-cli-<triple>.tar.gz` for macOS arm64, holding `coffer` + `coffer-daemon` + `coffer-mcp-shim`
- **And** the release contains a single aggregated `SHA256SUMS` file covering every artifact

### Scenario: post-build smoke test boots shim and gets JSON-RPC reply

- **Given** a freshly built bundle from the release matrix
- **When** the post-build smoke test (`scripts/smoke_test_bundle.sh`) is run against it
- **Then** the bundled `coffer-mcp-shim` starts, exchanges a JSON-RPC `initialize` message with the bundled daemon, and exits with status 0

## Functional Requirements

- **FR-D01**: The Tauri 2 shell MUST host the 002 web UI inside its window; desktop-only UI affordances activate behind the `isTauri()` guard already wired in spec 002.
- **FR-D02**: The desktop shell MUST supervise the daemon using the detect-or-spawn pattern from [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md) — connect to an existing daemon by reading `~/.coffer/daemon.json`, or spawn `coffer-daemon` as a detached process (`setsid` on POSIX, `DETACHED_PROCESS` on Windows) when none is reachable. The spawned daemon MUST survive the desktop window closing.
- **FR-D03**: The desktop shell MUST display a system-tray icon at all times while the app is running. The tray menu MUST include "Open", "Restart daemon", and "Quit" items. The "Restart daemon" item and the daemon-offline banner's Restart control both call the same rate-limited `restart_daemon` Tauri command.
- **FR-D04**: A window-close event MUST be intercepted and translated into a hide-to-tray action; closing the main window MUST NOT terminate the desktop process.
- **FR-D05**: Selecting "Quit" from the tray MUST call `app.exit()` (or platform-equivalent) so the desktop process actually exits and the tray icon disappears. Quit MUST NOT tear down the daemon — the daemon is a detached process (FR-D02) and keeps running after the desktop app exits, so MCP clients still work.
- **FR-D06**: On every launch, the desktop shell MUST idempotently deploy the bundled `coffer-mcp-shim` to a stable user-writable PATH directory (macOS/Linux: `~/.coffer/bin/`; Windows: `%LOCALAPPDATA%\Coffer\bin\`, with `%USERPROFILE%\Coffer\bin\` as fallback when unset). Deploy MUST be idempotent — an up-to-date on-disk binary is left untouched; a stale one is replaced atomically (temp-sibling copy + rename, executable bit set before the swap). Staleness is decided by a 3-signal heuristic (byte size, bundled-vs-deployed mtime, and a `.coffer-mcp-shim.version` sentinel), so cross-version upgrades that happen to be the same size are still detected.
- **FR-D07**: The Tauri bundle MUST declare `coffer-daemon` and `coffer-mcp-shim` as PyInstaller sidecars via `bundle.externalBin` in `desktop/tauri.conf.json`. No system Python dependency at runtime.
- **FR-D08**: The release pipeline MUST produce, per `v*` tag, two download tiers from the same PyInstaller binaries for **macOS arm64 only**: (a) the **CLI+desktop** tier — an unsigned macOS arm64 `.dmg` (named `*-unsigned.dmg`) plus a zipped `Coffer-unsigned-<triple>.app.zip`; and (b) the **CLI-only** tier — a `coffer-cli-<triple>.tar.gz` archive containing `coffer`, `coffer-daemon`, and `coffer-mcp-shim`. macOS x64 (Intel) and the Linux / Windows bundles are deliberately not built — those legs were never validated and the Intel runner pool is being deprecated; the acceptance matrix asserts a macOS-arm64-only build.
- **FR-D09**: The release pipeline MUST produce one aggregated `SHA256SUMS` file (generated in CI; concatenated across matrix legs in the release job) covering every artifact, so downloaders can verify integrity without trusting the GitHub Release UI alone.
- **FR-D10**: The desktop shell MUST integrate `tauri-plugin-opener` with the capabilities to open a filesystem path in an external application (`opener:allow-open-path`) and to reveal a path in the OS file manager (`opener:allow-reveal-item-in-dir`). This lets the read-only file viewers offer "open in editor" (opening the file or its containing folder in the user's preferred external editor — see 002 General settings) and "reveal in Finder"; on the web, where these OS actions are unavailable, the viewers fall back to "copy path".

## Success Criteria

- **SC-D01**: Cold-start budget — from desktop-app launch to the main window first paint is under 3 seconds on a 2022 MacBook Air (Apple silicon) when the daemon is not yet running; under 1 second when the daemon is already running.
- **SC-D02**: Bundle size budget — each platform installer is under 200 MB. Current observed range is 90–150 MB (PyInstaller interpreter + httpx + SQLAlchemy + aiosqlite + keyring + Pydantic + structlog + Typer + Tauri frontend).
- **SC-D03**: Every Acceptance Scenario in this document is covered by at least one test marked with `acceptance(spec="003-mcp-gateway-desktop", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-D04**: The post-build smoke test (`scripts/smoke_test_bundle.sh`) runs against the macOS arm64 artifacts in the release matrix and returns success — bundled shim talks to bundled daemon over loopback HTTP and gets a JSON-RPC `initialize` reply. (macOS arm64 is the only build leg; there is no Linux or Windows leg.)

## Distribution

Coffer ships **macOS (Apple Silicon) only** today. The release offers two download tiers, both built from the same PyInstaller binaries:

- **CLI-only** — a `coffer-cli-<triple>.tar.gz` archive (macOS arm64) containing `coffer`, `coffer-daemon`, and `coffer-mcp-shim`. For headless / no-GUI installs: run the daemon and point MCP clients at the shim, no desktop app. All three binaries stay co-located so detect-or-spawn (ADR-006) resolves `coffer-daemon` next to `coffer`.
- **CLI+desktop** — a Tauri 2 bundle (macOS arm64 `.dmg`) that embeds `coffer-daemon` and `coffer-mcp-shim` as sidecars plus the desktop shell and the 002 web UI.

See [`docs/decisions/ADR-008-distribution-pyinstaller-tauri-sidecar.md`](../../docs/decisions/ADR-008-distribution-pyinstaller-tauri-sidecar.md) for the architectural decision and [`docs/distribution/macos-notarization.md`](../../docs/distribution/macos-notarization.md) for the macOS notarisation runbook.

The release pipeline (`.github/workflows/release.yml`) runs PyInstaller for the macOS arm64 target, then both packages the three binaries into the `coffer-cli-<triple>.tar.gz` archive and drops `coffer-daemon` + `coffer-mcp-shim` into `desktop/binaries/` to build the Tauri bundle. Code-signing / notarisation is intentionally not wired yet — the bundle is renamed `*-unsigned` and ships unsigned until a paid Apple Developer ID is provisioned (a dedicated signed-release workflow is added then). Every artifact is covered by a single aggregated `SHA256SUMS` file.
