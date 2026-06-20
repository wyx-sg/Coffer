# Distribution

::: tip Core anchor
Coffer ships in two tiers from the same pair of PyInstaller binaries: a **CLI-only archive** for headless/developer use, and a **CLI+desktop Tauri bundle** for everyday desktop use. Neither tier requires a Python installation on the user's machine.
:::

## The problem this solves

Coffer's daemon and shim are Python applications. The target user population includes developers who do not have Python 3.12 installed at all, and end-users on macOS who have only the system Python (typically one or two versions behind). Asking these users to `pip install coffer` and manage a virtual environment would immediately disqualify Coffer as a daily-driver desktop tool.

The requirement, stated precisely in the spec: a user on a clean machine with no Python can reach `status: ready` from a single downloadable artifact with no manual steps beyond clicking through the installer.

## Developer install path

Developers who work from a source checkout bypass PyInstaller and the Tauri bundle entirely:

```bash
pip install -e ./backend[dev]
```

This places two console-script entry points on the developer's `PATH`:

- **`coffer`** — the management CLI (Typer application in `surfaces/cli/`)
- **`coffer-mcp-shim`** — the per-MCP-session stdio shim (`surfaces/shim/`)

The daemon runs directly as a Python process: `coffer daemon start` invokes the FastAPI/uvicorn startup path inside the installed package. No binary packaging, no build step, no sidecar orchestration. Changes to the Python source are visible immediately.

This developer path is well-documented and remains the primary contribution path. It is **not** the end-user distribution channel — the PyInstaller binaries serve that role.

## PyInstaller: standalone binaries

For end-user distribution, `make bundle-binaries` (driven by `scripts/build_binaries.sh`) runs PyInstaller on the current host against these spec files:

| Spec file                      | Output binary          | Includes                                                                                                                                                                                                                  |
| ------------------------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/coffer-daemon.spec`   | `dist/coffer-daemon`   | FastAPI, SQLAlchemy 2 / aiosqlite, Pydantic 2, `mcp`, `keyring`, Alembic, structlog, Typer, uvicorn, `tomlkit` / `yaml` (agent config editing), `sqlite_vec` (+ its native `vec0` loadable-extension data file), `markitdown`, `openai`, and the chat-agent stack (`langchain*` / `langgraph`) |
| `backend/coffer-mcp-shim.spec` | `dist/coffer-mcp-shim` | `httpx` only (shim is a thin loopback forwarder)                                                                                                                                                                          |
| `backend/coffer.spec`          | `dist/coffer`          | the management CLI (Typer app)                                                                                                                                                                                            |

::: warning Pending: the `coffer-callback` sidecar
A fourth process — the SeaTalk callback listener (`surfaces/callback/`, spawned by the daemon while a SeaTalk channel is enabled) — is **not yet a build target**. In source/dev runs the daemon spawns it as `python -m coffer.surfaces.callback`; in a frozen build `listener_spawn.py` expects a `coffer-callback` sibling next to the daemon binary and raises *"frozen build is missing the coffer-callback sibling binary"* if it is absent. Adding `backend/coffer-callback.spec` and wiring it into `build_binaries.sh` (so the frozen bundles ship the sidecar) is a known packaging item, tracked against spec 009-channels.
:::

PyInstaller bundles the Python interpreter, all dependencies, and the application code into a single-file executable. The user runs `coffer-daemon` directly; no `python` command, no `venv`, no `pip`. The shim binary is deliberately lean — it excludes all server-side dependencies because the shim only needs `httpx` to forward requests to the daemon over loopback HTTP. MCP clients that re-spawn the shim every session benefit from the shorter cold-start time a smaller binary provides.

Alembic migration files ship as data files inside the daemon binary via PyInstaller's `datas` mechanism. On first launch, the daemon runs `alembic upgrade head` against a fresh database before accepting connections — the end-user gets correct schema creation with no separate step.

The daemon binary also bundles the heavier knowledge/memory/chat dependencies (specs 006/007/008): `sqlite_vec` for the vector index, `markitdown` for document conversion, `openai` for embeddings, and the `langchain*` / `langgraph` chat-agent stack. These are imported lazily inside functions, so PyInstaller's static analysis cannot trace them — `coffer-daemon.spec` declares them explicitly as hidden imports so the frozen daemon can convert documents, embed, run vector retrieval, and drive the built-in chat agent.

::: warning Bundle verification — sqlite-vec native extension
`sqlite-vec` ships its loadable native extension (`vec0.dylib` / `vec0.so` / `vec0.dll`) as **package data**, not a Python submodule, so `collect_submodules` never captures it — `coffer-daemon.spec` adds it via `collect_data_files("sqlite_vec")`. If this data file is missing from a frozen build, the daemon cannot load the `vec0` extension and vector retrieval silently degrades to keyword-only (`VecIndex.available()` swallows the load failure). The release smoke test must therefore treat "the bundled daemon can load `vec0`" as an explicit bundle-verification item (per [ADR-012](/reference/adr/ADR-012-files-as-truth-sqlite-retrieval) and [ADR-008](/reference/adr/ADR-008-distribution-pyinstaller-tauri-sidecar)).
:::

::: tip Why PyInstaller, not alternatives
Two alternatives were explicitly considered and rejected for v0:

- **Nuitka / PyOxidizer**: AOT compilation produces smaller and faster binaries, but lengthens the build cycle significantly and requires platform-specific compilers in CI. Switching packager later is a bounded, reversible change — nothing in the daemon's runtime contract is PyInstaller-specific.
- **Requiring system Python**: directly violates the requirement that a user with no Python can install Coffer. Even on Linux, the distro-shipped Python is typically one version behind; users encounter wheel-build errors for `aiosqlite` or `pydantic-core`.
  :::

## Two download tiers

The same two PyInstaller binaries feed both distribution tiers:

### Tier 1: CLI-only archive

A `coffer-cli-<triple>` archive — `.tar.gz` (macOS and Linux) — containing:

- `coffer` (the management CLI)
- `coffer-daemon` (standalone executable)
- `coffer-mcp-shim` (standalone executable)
- `coffer-callback` (the SeaTalk callback-listener sidecar — pending; see the packaging note above) once it becomes a build target
- A SHA-256 checksum file

This tier targets headless servers, CI environments, and developers who want the standalone binaries without a desktop app. The user extracts the archive, runs `coffer-daemon`, places `coffer-mcp-shim` on their `PATH`, and points MCP clients at the shim. No Tauri, no GUI, no desktop integration.

### Tier 2: CLI+desktop Tauri bundle

A platform-native installer (DMG on macOS, AppImage and `.deb` on Linux) that embeds:

- The `coffer-daemon` and `coffer-mcp-shim` PyInstaller binaries as **Tauri sidecars** (and `coffer-callback` once it is a build target — see the packaging note above)
- The Tauri 2 desktop shell (Rust + WebView)
- The web UI from spec 002

The Tauri sidecar mechanism (`bundle.externalBin` in `desktop/tauri.conf.json`) is the official Tauri 2 way to ship a native helper binary alongside an app. It handles per-platform packaging details: code-signing identity, `chmod +x` on Linux — things that would be fiddly to manage manually. Tauri embedded resources (a different mechanism) are for static assets, not executables; the sidecar mechanism is the correct choice for runnable binaries.

::: tip Why not a single desktop-only download?
Headless servers and CI boxes cannot run a Tauri app. Providing only a desktop bundle would leave those environments with no runnable artifact. The CLI-only archive is a first-class release tier, not a post-v0 afterthought.
:::

## Tauri desktop integration

The desktop shell does more than wrap the web UI in a window. Key responsibilities (owned by spec 003):

**Daemon supervision.** On launch, the desktop shell reads `~/.coffer/daemon.json`. If a reachable daemon is already running (any entry point may have started it — the CLI, the shim, or a previous desktop launch), the shell connects to it. If not, it spawns `coffer-daemon` as a detached process (`setsid` on POSIX) so the daemon survives the desktop window closing. The daemon's `detect-or-spawn` pattern ensures no duplicate daemon processes.

**Shim auto-deploy to PATH.** On every desktop launch, the shell idempotently deploys the bundled `coffer-mcp-shim` to a stable user-writable directory:

- macOS / Linux: `~/.coffer/bin/coffer-mcp-shim`

A staleness check handles upgrades: the on-disk binary is compared against the bundled one on **size + mtime + a version sentinel**, and is left untouched when they match (no-op on repeated launches). Any mismatch triggers an atomic replace. This means users who upgrade Coffer via a new DMG or package automatically get the updated shim on next launch, without manual PATH management.

**Tray icon.** The desktop app runs as a system tray icon after the main window is closed. Closing the window hides it; the daemon and tray remain. The tray menu provides: Open (restore the window), Restart daemon, and Quit (which calls `app.exit()` and actually terminates the process).

## Release pipeline

The CI release matrix (`.github/workflows/release.yml`) runs on every `v*` tag across two target platforms (macOS arm64, Linux x64) and produces:

**Desktop installers (CLI+desktop tier)**:

- macOS arm64 DMG
- Linux x64 AppImage
- Linux x64 `.deb`

**CLI-only archives (CLI-only tier)**:

- `coffer-cli-darwin-arm64.tar.gz`
- `coffer-cli-linux-x86_64.tar.gz`

macOS x64 (Intel) and Windows are not built: GitHub's Intel macOS runner pool is being deprecated and reliably starves the `macos-13` job (it sits "waiting for a runner" indefinitely), and PyInstaller cannot cross-compile the x86_64 sidecars from the arm64 runner.

Every artifact ships with a `<artifact>.sha256` checksum file generated in CI.

Before upload, each bundle runs a post-build smoke test (`scripts/smoke_test_bundle.sh`): the script boots the bundled `coffer-daemon` to `status: ready` and has the bundled `coffer-mcp-shim` exchange a JSON-RPC `initialize` message with it over loopback. A non-zero exit from the smoke test fails the release. Every bundle is smoke-tested across both the macOS and Linux release legs — there is no Windows leg. The script uses a backgrounded watchdog rather than GNU `timeout`, so it runs cleanly on both the macOS and Linux legs.

## macOS notarisation

macOS Gatekeeper will quarantine unsigned applications on first launch. macOS notarisation — Apple's process for attesting that an app is free of known malware — is currently a non-goal for Coffer: it requires a paid Apple Developer account.

Until notarisation is enabled, users installing the macOS DMG must clear the quarantine attribute manually on first launch:

```bash
xattr -d com.apple.quarantine /Applications/Coffer.app
```

The full runbook for enabling signing and notarisation once a Developer ID certificate is available is in `docs/distribution/macos-notarization.md`.

## See also

- [ADR-008: Distribution — PyInstaller + Tauri sidecar](/reference/adr/ADR-008-distribution-pyinstaller-tauri-sidecar) — decision record, rejected alternatives, and revision history
- [Spec 003 reference](/reference/specs/003-mcp-gateway-desktop/spec) — desktop shell acceptance scenarios and functional requirements
