# Implementation Plan: Desktop App

**Spec**: [./spec.md](./spec.md)
**Status**: Accepted

## Summary

A small Tauri shell around the frontend build the daemon already serves. It adds
the four things a browser tab cannot do for itself — an application window with
a Dock icon, a resident tray, detect-or-spawn at launch, and a credential
handshake for a page nobody served — and deliberately adds nothing else.

See [./spec.md](./spec.md) for the user-visible contract,
[The Desktop Shell Returns](../../docs/decisions/desktop-shell-over-a-shared-frontend.md)
for why the shell was restored after being retired, and
[PyInstaller Distribution](../../docs/decisions/distribution-pyinstaller.md)
for how its binaries are frozen.

## Technical Context

| Dimension                | Value                                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------------------------ |
| **Language / Version**   | Rust (Tauri 2), over the existing TypeScript frontend build                                               |
| **Primary Dependencies** | Tauri 2 core + tray; `log`; the standard library for process spawning. No dialog plugin, no opener plugin. |
| **Storage**              | None. The shell reads `~/.coffer/daemon.json` and appends to `~/.coffer/logs/daemon.log`; it writes no state of its own. |
| **Testing**              | `cargo test` over the crate's pure functions — outside every verification gate; see spec.md `## Assumptions`. |
| **Target Platforms**     | macOS arm64 only.                                                                                          |
| **Constraints**          | No second frontend build; no reimplementation of a daemon route; no writes to `~/.coffer/bin/`.             |

## Constitution Check

| Constitutional clause               | Compliance | Notes                                                                                                        |
| ----------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)** | ✅         | The shell talks to loopback and to the local filesystem. Its content policy admits nothing else.               |
| **II. Spec-as-Truth**               | ✅         | The acceptance scenarios in spec.md are this shell's contract.                                                 |
| **III. Open-Source-Readiness**      | ✅         | One extra language in the repo, confined to `desktop/`, and a build step nobody needs unless they build a release. |
| **Network defaults: loopback-only** | ✅         | `connect-src` permits `http://127.0.0.1:*` and the IPC scheme, and nothing else.                               |

**Languages.** The constitution's language list is Python and TypeScript; Rust
enters through Tauri and stays inside `desktop/`. That is the cost the ADR priced
and accepted, bounded by the fact that no verification gate grows a toolchain.

## Project Structure

### Documentation (this feature)

```text
specs/desktop-app/
├── spec.md              # user-visible contract
├── plan.md              # this file
└── quickstart.md        # how a user installs and uses it
```

No `contracts/` — the shell exposes no HTTP surface. See spec.md
`## Assumptions`.

### Source code

```text
desktop/
├── tauri.conf.json        # window, tray, CSP (FR-003), externalBin (FR-013), bundle targets
├── binaries/              # the four frozen binaries, placed by the release build
├── capabilities/          # the permission set — deliberately minimal (FR-011)
└── src/
    ├── main.rs            # entry
    ├── lib.rs             # app setup; installs the logger first (FR-012)
    ├── logging.rs         # structlog-shaped JSON into ~/.coffer/logs/daemon.log
    ├── discovery.rs       # read daemon.json, HTTP liveness probe, shutdown request, wait-for-free
    ├── resolve.rs         # the five-step resolution chain (FR-006)
    ├── daemon.rs          # the IPC commands: handshake, restart policy, rate limit (FR-004/007/008)
    ├── spawn.rs           # detached spawn that outlives the app (FR-009)
    ├── env_path.rs        # login-shell $PATH probe (FR-010)
    ├── sidecar.rs         # locating the bundled binaries
    └── tray.rs            # tray menu and the close-to-tray decision (FR-001)
```

```text
frontend/
└── dist/                  # ONE build, consumed by this bundle and by the daemon's static mount
```

## Layers and boundaries

**The chain's order is correctness, not preference.** `resolve.rs` asks the
liveness probe first and the three binary-location questions afterwards, because
those three answer *which binary would we spawn* while the first answers
*whether to spawn at all*. Reversed, a bundled build opens a second daemon beside
the one the user already started; under the fixed-port default that rival cannot
bind, so an app that should simply have attached reports a port conflict instead.

**The probe is HTTP, not TCP.** `discovery.rs` keeps both: a bare connect answers
"is the socket gone", used after a shutdown request, and a status probe answers
"is a Coffer daemon here". Using the first for the second is how a port squatter
becomes a phantom daemon.

**Restart holds one lock across the whole operation.** `daemon.rs` takes the
rate-limit mutex for check, stop, spawn and timestamp together, which serialises
concurrent restarts and closes the double-spawn race: the second caller sees
either the recorded timestamp or the now-running daemon. The timestamp is written
only after a spawn succeeds, so a failure does not consume the window.

**Spawning bypasses the framework's sidecar API deliberately.** The managed
sidecar tears children down on app shutdown, which is exactly wrong for a daemon
that serves agents whether or not a window is open. `spawn.rs` uses a plain
detached process and redirects its output into the shared daemon log.

**The shell is a reader of other specs' files, never a writer.** It reads
`daemon.json` (spec daemon), appends to `daemon.log` (spec daemon), and consumes
`frontend/dist` (spec web-ui's build). It writes nothing under `~/.coffer/` but
log lines.

## Complexity Tracking

| Decision                                      | Why needed                                                                                                    | Simpler alternative rejected because                                                                                       |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Host the UI as a local asset rather than loading the daemon's origin | The window must render before the daemon answers, or a launch after reboot shows a connection error. | A thin wrapper around `http://127.0.0.1:<port>` is a bookmarked browser window with extra steps, and shows the port in the chrome. |
| Bundle four frozen binaries in the `.dmg`     | "Desktop app" has to mean self-contained; the first launch then leaves the CLI on disk too.                    | An app that asks the user to install a runtime first is a wrapper around a prerequisite.                                     |
| Probe the login shell for `$PATH`             | A Finder-launched app inherits a minimal `$PATH`, and the MCP upstreams a daemon spawns need the real one.     | Hard-coding common locations breaks on every version manager; doing nothing breaks `npx`/`uvx` silently.                     |

## Cross-Reference Index

- Spec contract: [spec.md](./spec.md)
- Quickstart: [quickstart.md](./quickstart.md)
- Decision records: [The Desktop Shell Returns](../../docs/decisions/desktop-shell-over-a-shared-frontend.md), [PyInstaller Distribution](../../docs/decisions/distribution-pyinstaller.md), [The Daemon Serves Its Token in the Page](../../docs/decisions/daemon-serves-the-token-in-the-page.md)
- Constitution: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
