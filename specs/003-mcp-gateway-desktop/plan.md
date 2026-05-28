# Implementation Plan: 003 — MCP Gateway Desktop

**Branch**: `feature/003-mcp-gateway-desktop`
**Date**: 2026-05-28
**Spec**: [./spec.md](./spec.md)
**Status**: Accepted

## Summary

Wrap the 002 web UI in a Tauri 2 desktop shell, supervise the headless daemon
via [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md)'s
detect-or-spawn pattern, deploy the bundled `coffer-mcp-shim` to a stable
user-writable PATH location on every launch, and package the result as
single-bundle installers for macOS (arm64 + x64), Linux x64, and Windows
x64. The PyInstaller-built daemon + shim binaries are carried inside the
Tauri bundle as `bundle.externalBin` sidecars per
[ADR-007](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md).

This spec adds **no new backend**, **no new resource kinds**, and **no new
UI screens**. The desktop-only `AppSettings` React component shipped in 002
behind an `isTauri()` guard is the only frontend touchpoint.

See [./spec.md](./spec.md) for the user-visible contract,
[./quickstart.md](./quickstart.md) for the end-user walkthrough, and
[ADR-007](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md)
for the distribution-architecture decision.

## Technical Context

| Dimension                | Value                                                                                                                                                                                                                                                      |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**   | Rust 1.78+ (Tauri 2 crate); reuses Python 3.12 from the daemon / shim (PyInstaller-bundled).                                                                                                                                                               |
| **Primary Dependencies** | Tauri 2 (`tauri`, `tauri-build`); `tauri-plugin-autostart` (launch-at-login set/get); `tauri-plugin-shell` only as needed for sidecar spawn; the 002 frontend bundle (loaded from `dist/`).                                                                |
| **Sidecar Binaries**     | `coffer-daemon` and `coffer-mcp-shim`, built per platform via `scripts/build_binaries.sh` driving the PyInstaller specs in `backend/`.                                                                                                                     |
| **Daemon Discovery**     | `~/.coffer/daemon.json` (port + token + pid), shared with the CLI and shim. See [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md).                                                                                                         |
| **Shim PATH target**     | macOS / Linux: `~/.coffer/bin/`. Windows: `%LOCALAPPDATA%\Coffer\bin\` (fallback `%USERPROFILE%\Coffer\bin\` when unset).                                                                                                                                  |
| **Testing**              | Rust unit tests (`#[cfg(test)]`) for shim-deploy, daemon-supervisor, and tray-handler logic; Playwright (`e2e/`) for tray + window scenarios when running under `make dev-tauri`; CI smoke test (`scripts/smoke_test_bundle.sh`) for the bundled artifact. |
| **Target Platforms**     | macOS 12+ (arm64 + x64, separate DMGs), Linux x64 (AppImage + deb), Windows 10+ x64 (MSI + NSIS).                                                                                                                                                          |
| **Project Type**         | Native desktop shell wrapping a SPA. The Tauri crate lives in `desktop/`; the frontend bundle is `frontend/dist/` (built by 002's Vite pipeline).                                                                                                          |
| **Performance Goals**    | Cold-start < 3 s with no daemon running, < 1 s with daemon already running (SC-D01). PyInstaller sidecars carry the cold-start floor.                                                                                                                      |
| **Constraints**          | Local-first (loopback-only daemon); no public-internet calls; no analytics. Each bundle file ≤ 200 MB (SC-D02). No new constitutional dependencies — all picks were already approved by ADR-006 / ADR-007.                                                 |
| **Scale / Scope**        | Single-user desktop; one daemon process; one shim per MCP client; ≤ 30 registered resources (consistent with 001 / 002 limits).                                                                                                                            |

## Constitution Check

| Constitutional clause                     | Compliance | Notes                                                                                                                                                                                              |
| ----------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)**       | OK         | Daemon stays loopback-only; the desktop shell never reaches the public internet. Auto-update is explicitly out of scope so no telemetry / update-server call ships.                                |
| **II. Spec-as-Truth**                     | OK         | Spec committed before code; every acceptance scenario has a covering test (acceptance audit).                                                                                                      |
| **III. Open-Source-Readiness**            | OK         | Tauri 2 (MIT/Apache-2.0) and `tauri-plugin-autostart` (MIT) are permissive-licensed; PyInstaller is GPL with a runtime-only exception that does not contaminate bundled binaries.                  |
| **Languages**                             | OK         | Rust is allowed for the desktop shell per the constitution Languages clause; the daemon and shim remain Python 3.12.                                                                               |
| **Architecture: layered**                 | OK         | Desktop crate is a thin shell — supervision, tray, and shim deploy live in dedicated modules; the web UI from 002 is the view layer.                                                               |
| **Persistence: SQLite for control plane** | OK         | This spec owns no persistence; the daemon does. The shell reads `~/.coffer/daemon.json` (not SQLite) to discover the daemon — the discovery file is part of the runtime contract owned by ADR-006. |
| **Credentials: keychain only**            | OK         | Spec owns no credentials. The autostart preference is stored by `tauri-plugin-autostart` (OS-native, not the keychain).                                                                            |
| **Network defaults: loopback-only**       | OK         | The shell talks to the daemon on `127.0.0.1:<port>` from `daemon.json`; no other HTTP origin is reached.                                                                                           |

## Project Structure

### Documentation (this feature)

```text
specs/003-mcp-gateway-desktop/
├── spec.md           # user-visible contract (committed)
├── plan.md           # this file
└── quickstart.md     # end-user walkthrough (download → install → first launch → tray)
```

This folder deliberately has **no** `data-model.md` (no backend data here)
and **no** `tasks.md` (the work is tracked at the user-story / PR level —
the unit of change is "one desktop concern" — shim deploy, tray, autostart,
release pipeline — and each lands as one PR).

### Source code (delivered in this PR)

```text
desktop/
├── Cargo.toml                        # tauri 2 crate
├── tauri.conf.json                   # window config, bundle.externalBin sidecars, macOS signingIdentity stub
├── icons/                            # platform tray + app icons + embedded fallback PNG
├── binaries/                         # PyInstaller output landing zone (gitignored; populated in CI)
├── src/
│   ├── main.rs                       # entry — tauri::Builder
│   ├── lib.rs                        # app setup, tray menu wiring, window-close interceptor
│   ├── daemon_supervisor.rs          # detect-or-spawn helper (POSIX setsid / Windows DETACHED_PROCESS)
│   ├── shim_deploy.rs                # idempotent shim copy with size-mismatch heuristic
│   └── tray.rs                       # tray menu (Open / Restart daemon / Quit)
└── tests/                            # rust unit tests for the above modules

scripts/
├── build_binaries.sh                 # drives PyInstaller specs in backend/ (already exists from 001)
└── smoke_test_bundle.sh              # CI post-build smoke test (already exists)

.github/workflows/
└── release.yml                       # cross-platform release matrix + per-artifact SHA-256
```

### Extension point: the daemon-supervisor module

`desktop/src/daemon_supervisor.rs` is the Rust-side mirror of the Python
`detect-or-spawn` helper used by the CLI and shim. It reads
`~/.coffer/daemon.json`, probes the recorded PID, and spawns
`coffer-daemon` as a detached process when no live daemon is found.
"Detached" means `setsid` on POSIX and `CREATE_NEW_PROCESS_GROUP |
DETACHED_PROCESS` on Windows — this is what makes the daemon outlive the
desktop window's close-to-tray.

### Shim deploy strategy

`desktop/src/shim_deploy.rs` runs on every desktop launch:

1. Resolve the target directory (`~/.coffer/bin/` on macOS/Linux,
   `%LOCALAPPDATA%\Coffer\bin\` on Windows, falling back to
   `%USERPROFILE%\Coffer\bin\` when `%LOCALAPPDATA%` is unset).
2. Probe the bundle for the `coffer-mcp-shim` sidecar binary. The probe
   checks the sidecar's expected location first, then walks one directory
   up — necessary because Tauri places sidecars in different relative
   locations under `target/debug/` (dev) and `Resources/` (release).
3. Compare the bundled shim's byte size to the on-disk shim (when present).
   Equal → no-op. Differing → atomic replace (`tempfile` + `rename`).

The PATH-membership prompt is shown once on first launch when the target
directory is not on `PATH` (handled by 002's `AppSettings` tab; the shell
just deploys the binary).

### Build matrix

| Platform | Architecture | Installer formats     | Cross-build host    |
| -------- | ------------ | --------------------- | ------------------- |
| macOS    | arm64        | `.dmg`                | macos-14 runner     |
| macOS    | x64          | `.dmg`                | macos-13 runner     |
| Linux    | x64          | `.AppImage`, `.deb`   | ubuntu-22.04 runner |
| Windows  | x64          | `.msi`, `.exe` (NSIS) | windows-2022 runner |

Each artifact is paired with a `<artifact>.sha256` file generated in the
same job step. macOS notarization runs only when the Apple Developer secrets
are present (see [`docs/distribution/macos-notarization.md`](../../docs/distribution/macos-notarization.md));
unsigned DMGs continue to ship until the secrets land.

### File size caps

- Each Tauri bundle ≤ 200 MB (SC-D02). Current observed: 90–150 MB.
- Each PyInstaller sidecar ≤ 100 MB. Current observed: daemon ~70 MB, shim ~30 MB.
- Rust source files in `desktop/src/` ≤ 250 LOC each (per `scripts/check_file_sizes.py`).

## Phases (high-level)

Phases are **delivery boundaries**, not atomic-task breakdowns.

### Phase 1 — Tauri shell + frontend mount

`tauri.conf.json` (window, sidecars, icons), `desktop/src/main.rs` +
`lib.rs`, Vite frontend mount.

**Done when:** `cargo tauri dev` launches the 002 web UI inside the Tauri
window; the `isTauri()` guard is true on first render.

### Phase 2 — Daemon supervisor

`daemon_supervisor.rs` — detect-or-spawn against `~/.coffer/daemon.json`,
detached spawn (`setsid` / `DETACHED_PROCESS`).

**Done when:** the shell connects to an already-running daemon without
duplicating, spawns one when none is running, and the spawned daemon
survives desktop-app close (US7 scenarios).

### Phase 3 — Tray menu + close-to-tray

`tray.rs` (Open / Restart daemon / Quit), window-close interceptor in
`lib.rs`.

**Done when:** US9's tray scenarios pass and US5's "close to tray, not exit"
scenario passes.

### Phase 4 — Autostart + AppSettings wiring

`tauri-plugin-autostart` integration with set/get exposed to the JS bridge;
002's `AppSettings` component picks up the toggle.

**Done when:** US5's "launch at login" scenario passes.

### Phase 5 — Shim auto-deploy

`shim_deploy.rs` — idempotent copy with size-mismatch heuristic, parent-dir
probing, Windows PATH fallback.

**Done when:** US8's three scenarios pass.

### Phase 6 — Release pipeline + smoke test

`.github/workflows/release.yml` runs the build matrix; each artifact is
accompanied by a SHA-256; `scripts/smoke_test_bundle.sh` runs against each
bundle.

**Done when:** US6's two build-pipeline scenarios pass and a draft release
on a `v*-rc` tag produces all four installers green.

## Complexity Tracking

| Decision                                                            | Why needed                                                                                                                                                         | Simpler alternative rejected because                                                                                                                                                                          |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tauri 2 over Electron                                               | Smaller bundle (no embedded Chromium), native OS controls, Rust core — fits Coffer's "local-first lightweight" posture.                                            | Electron would inflate each installer by ~150 MB on top of the PyInstaller sidecars and pull in a full Node runtime; the visual-language polish from 002 doesn't need a Chromium-specific feature.            |
| Detached daemon spawn (setsid / DETACHED_PROCESS)                   | Required for the daemon to outlive the desktop window's close-to-tray — otherwise OS process tree cleanup kills the daemon when the Tauri process exits.           | A foreground child process leaks the close-to-tray scenario; reparenting to PID 1 is what `setsid` and `DETACHED_PROCESS` are for.                                                                            |
| Shim deploy on every launch (idempotent)                            | The desktop shell is the only entry point that knows where the bundled shim lives; deploying once-only (at install time) would miss in-place bundle upgrades.      | A separate "shim updater" service would be more moving parts; the size-mismatch heuristic is a few lines and runs in microseconds when the binary is already up to date.                                      |
| Two separate macOS DMGs (arm64 + x64) instead of a universal binary | Tauri 2's release pipeline emits one DMG per `cargo tauri build`; a universal DMG would require a separate `lipo` post-processing step we don't currently run.     | A universal binary would halve the macOS download count at the cost of doubling per-user download size and complicating the release matrix; two DMGs is simpler and matches the current release.yml behavior. |
| `tauri-plugin-autostart` over hand-rolling launchd / Task Scheduler | Cross-platform launch-at-login is non-trivial (launchd plist + systemd user unit + Windows Task Scheduler / Run key); the plugin is already maintained and tested. | Hand-rolling per-platform launch-at-login multiplies bug surface and tests across three OSes for zero functional gain.                                                                                        |

## Cross-Reference Index

- Spec contract: [spec.md](./spec.md)
- Quickstart: [quickstart.md](./quickstart.md)
- Distribution decision: [ADR-007](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md)
- Daemon detect-or-spawn: [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md)
- macOS notarization runbook: [`docs/distribution/macos-notarization.md`](../../docs/distribution/macos-notarization.md)
- Web UI host: [`specs/002-ui-shell/spec.md`](../002-ui-shell/spec.md)
- Architecture overview: [`.specify/memory/architecture.md`](../../.specify/memory/architecture.md)
- Constitution: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
