# Distribution

::: tip Core anchor
Coffer ships as **one tier**: a `coffer-cli-<triple>.tar.gz` archive of PyInstaller binaries, published per `v*` tag alongside a single aggregated `SHA256SUMS`. It requires no Python installation on the user's machine, and the management UI is a web UI that the **daemon itself serves** — there is no separate desktop application to install or update.
:::

## The problem this solves

Coffer's daemon and shim are Python applications. The target user population includes developers who do not have Python 3.12 installed at all, and end-users on macOS who have only the system Python (typically one or two versions behind). Asking these users to `pip install coffer` and manage a virtual environment would immediately disqualify Coffer as a daily-driver tool.

The requirement, stated precisely in the spec: a user on a clean machine with no Python can reach `status: ready` from a single downloadable artifact with no manual steps beyond extracting it.

## Why there is no desktop shell

Coffer used to ship a second tier — a Tauri 2 desktop application that embedded the web UI in a native window. It was removed, and the judgement was about **the operating cost of every update**, not about lines of code.

Every change to the product had to travel through a rebuild *and* a reinstall before it could be seen, and the built artifact kept drifting away from source. Two incidents are on the record: a build produced before fetching shipped an app that was quietly running stale code; and because the app was built from a separately pinned directory, UI bug reports had to be re-verified against `main` before they could be trusted at all. Neither failure mode survives in the web form. Restart the daemon, hard-refresh the browser, and you are looking at the current code.

What the desktop shell genuinely owned — serving the UI, and deploying helper binaries onto the user's machine — moved into the daemon, which is documented below.

## Developer install path

Developers who work from a source checkout bypass PyInstaller entirely:

```bash
pip install -e ./backend[dev]
```

This places two console-script entry points on the developer's `PATH`:

- **`coffer`** — the management CLI (Typer application in `surfaces/cli/`)
- **`coffer-mcp-shim`** — the per-MCP-session stdio shim (`surfaces/shim/`)

The daemon runs directly as a Python process: `coffer daemon start` invokes the FastAPI/uvicorn startup path inside the installed package. No binary packaging, no build step. Changes to the Python source are visible immediately, and a source install needs no binary deployment at all — `pip install` has already put the console scripts on `PATH`.

This developer path is well-documented and remains the primary contribution path. It is **not** the end-user distribution channel — the PyInstaller binaries serve that role.

## PyInstaller: standalone binaries

For end-user distribution, `make bundle-binaries` (driven by `scripts/build_binaries.sh`) runs PyInstaller on the current host against these spec files:

| Spec file                      | Output binary          | Includes                                                                                                                                                                                                                  |
| ------------------------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/coffer-daemon.spec`   | `dist/coffer-daemon`   | FastAPI, SQLAlchemy 2 / aiosqlite, Pydantic 2, `mcp`, `keyring`, Alembic, structlog, Typer, uvicorn, `tomlkit` / `yaml` (agent config editing), `sqlite_vec` (+ its native `vec0` loadable-extension data file), `markitdown`, `openai`, and the chat-agent stack (`langchain*` / `langgraph`) |
| `backend/coffer-mcp-shim.spec` | `dist/coffer-mcp-shim` | `httpx` only (shim is a thin loopback forwarder)                                                                                                                                                                          |
| `backend/coffer.spec`          | `dist/coffer`          | the management CLI (Typer app)                                                                                                                                                                                            |

PyInstaller bundles the Python interpreter, all dependencies, and the application code into a single-file executable. The user runs `coffer-daemon` directly; no `python` command, no `venv`, no `pip`. The shim binary is deliberately lean — it excludes all server-side dependencies because the shim only needs `httpx` to forward requests to the daemon over loopback HTTP. MCP clients that re-spawn the shim every session benefit from the shorter cold-start time a smaller binary provides.

Alongside these, the release archive carries the **runtime helper binaries** the daemon spawns as child processes: `coffer-callback` (the SeaTalk callback listener, `surfaces/callback/`, spawned while a SeaTalk channel is enabled) and `whisper-cli` (local speech-to-text). In a source/dev run the daemon spawns the callback listener as `python -m coffer.surfaces.callback`; in a frozen build `listener_spawn.py` looks for a `coffer-callback` sibling next to the daemon binary. This sibling relationship is exactly why the daemon — not an installer — owns deploying these binaries (see [Binary deployment at frozen start](#binary-deployment-at-frozen-start)).

Alembic migration files ship as data files inside the daemon binary via PyInstaller's `datas` mechanism. On first launch, the daemon runs `alembic upgrade head` against a fresh database before accepting connections — the end-user gets correct schema creation with no separate step.

The daemon binary also bundles the heavier knowledge and chat dependencies (specs 007/008): `sqlite_vec` for the vector index, `markitdown` for document conversion, `openai` for embeddings, and the `langchain*` / `langgraph` chat-agent stack. These are imported lazily inside functions, so PyInstaller's static analysis cannot trace them — `coffer-daemon.spec` declares them explicitly as hidden imports so the frozen daemon can convert documents, embed, run vector retrieval, and drive the built-in chat agent.

The built web UI (spec 002) also ships as data files inside the daemon binary, which is what lets the frozen daemon serve the UI from its own origin.

::: warning Bundle verification — sqlite-vec native extension
`sqlite-vec` ships its loadable native extension (`vec0.dylib` / `vec0.so` / `vec0.dll`) as **package data**, not a Python submodule, so `collect_submodules` never captures it — `coffer-daemon.spec` adds it via `collect_data_files("sqlite_vec")`. If this data file is missing from a frozen build, the daemon cannot load the `vec0` extension and vector retrieval silently degrades to keyword-only (`VecIndex.available()` swallows the load failure). The release smoke test must therefore treat "the bundled daemon can load `vec0`" as an explicit bundle-verification item (per [ADR-012](/reference/adr/ADR-012-files-as-truth-sqlite-retrieval) and [ADR-008](/reference/adr/ADR-008-distribution-pyinstaller)).
:::

::: tip Why PyInstaller, not alternatives
Two alternatives were explicitly considered and rejected for v0:

- **Nuitka / PyOxidizer**: AOT compilation produces smaller and faster binaries, but lengthens the build cycle significantly and requires platform-specific compilers in CI. Switching packager later is a bounded, reversible change — nothing in the daemon's runtime contract is PyInstaller-specific.
- **Requiring system Python**: directly violates the requirement that a user with no Python can install Coffer. Even on Linux, the distro-shipped Python is typically one version behind; users encounter wheel-build errors for `aiosqlite` or `pydantic-core`.
  :::

## One download tier

Every release publishes a single kind of user-facing artifact (**FR-022**): a `coffer-cli-<triple>.tar.gz` archive containing

- `coffer` (the management CLI)
- `coffer-daemon` (standalone executable, with the built web UI inside it)
- `coffer-mcp-shim` (standalone executable)
- the runtime helper binaries the daemon spawns — `coffer-callback` and `whisper-cli`

The user extracts the archive, runs `coffer-daemon` (or `coffer daemon start`), and opens the UI with `coffer open`. The same archive serves headless servers, CI environments and workstations, because the UI is a browser page rather than a native application: on a headless box you simply never open it.

Instead of a per-file `.sha256` sidecar file, the release publishes **one aggregated `SHA256SUMS`** covering every artifact in the release (**FR-023**), so a single `shasum -c SHA256SUMS` verifies the whole download set.

## The daemon serves the web UI

The daemon serves the built web UI itself, as static files, at its own loopback origin (**FR-024**). The UI and the REST API are therefore **same-origin**: the page is fetched from `http://127.0.0.1:<port>/` and calls `http://127.0.0.1:<port>/api/v1/`. There is no native window, no tray icon, and no build-time branching in the frontend for "am I inside a desktop shell".

`coffer open` is the entry point (**FR-025**):

1. It reads the daemon's port and API token from `~/.coffer/daemon.json` (mode `0600`).
2. It calls an authenticated endpoint to mint a **single-use, short-lived code** — valid for about a minute.
3. It opens the browser at the daemon's origin with that code in the URL **fragment**.
4. The page exchanges the code for the API token and keeps the token in `localStorage`.

The token itself never appears in a URL. Putting it there would write it into browser history, which contradicts the loopback-plus-token posture of spec 001 (FR-012 / FR-013). The exchange code is single-use and expires within about a minute, so its presence in history is inert.

Because the UI is same-origin with the API, CORS is **same-origin by default**. The Vite dev-server origins remain available behind the existing `COFFER_DEV_CORS` opt-in for frontend development. See [Security](/architecture/security) for the full posture.

## Binary deployment at frozen start

The desktop shell used to deploy `coffer-mcp-shim` onto the user's `PATH` at every launch. The daemon now does it at startup, and only when it detects that it is running as a frozen build (**FR-026**). It idempotently copies its sibling binaries into `~/.coffer/bin/`:

- macOS / Linux: `~/.coffer/bin/coffer-mcp-shim`, plus `coffer-daemon`, `coffer-callback` and `whisper-cli`

The mechanics are unchanged from the desktop implementation: an atomic temp-copy-then-rename, guarded by the same **three-signal staleness check** — byte size, mtime, and a version sentinel. If all three match, the deployment is a no-op; any mismatch triggers an atomic replace, so upgrading Coffer by extracting a newer archive updates the deployed binaries on the next daemon start with no manual `PATH` management.

The daemon is the natural owner of this step because it is the process that actually spawns `coffer-callback` and `whisper-cli` at runtime and needs them at known sibling paths. A source install skips deployment entirely — it is not a frozen build, and `pip install` has already put the console scripts on `PATH`.

## Release pipeline

The CI release workflow (`.github/workflows/release.yml`) runs on every `v*` tag and produces the single CLI archive per built target — currently macOS arm64 — plus the aggregated `SHA256SUMS`.

macOS x64 (Intel) and Windows are not built: GitHub's Intel macOS runner pool is being deprecated and reliably starves the `macos-13` job (it sits "waiting for a runner" indefinitely), and PyInstaller cannot cross-compile x86_64 binaries from the arm64 runner.

Before upload, the archive runs a post-build smoke test (`scripts/smoke_test_bundle.sh`): the script boots the bundled `coffer-daemon` to `status: ready` and has the bundled `coffer-mcp-shim` exchange a JSON-RPC `initialize` message with it over loopback. A non-zero exit from the smoke test fails the release. The script uses a backgrounded watchdog rather than GNU `timeout`, so it runs cleanly on macOS.

## macOS Gatekeeper

macOS Gatekeeper quarantines downloaded, unsigned executables on first run. Code-signing and notarisation — Apple's process for attesting that a binary is free of known malware — are currently a non-goal for Coffer: they require a paid Apple Developer ID, which has not been provisioned.

Until one is, users clear the quarantine attribute on the binaries they extracted from the archive:

```bash
xattr -d com.apple.quarantine ~/coffer/coffer ~/coffer/coffer-daemon ~/coffer/coffer-mcp-shim
```

## See also

- [ADR-008: Distribution — PyInstaller-bundled daemon, shim and CLI](/reference/adr/ADR-008-distribution-pyinstaller) — decision record, rejected alternatives, and revision history
- [Spec 001 reference](/reference/specs/001-mcp-gateway/spec) — FR-022 single-tier archive, FR-023 aggregated `SHA256SUMS`, FR-024 daemon-served web UI, FR-025 `coffer open`, FR-026 frozen-start binary deployment
